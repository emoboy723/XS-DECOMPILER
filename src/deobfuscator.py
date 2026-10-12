"""Conservative JavaScript literal transforms. No eval, JS execution or runtime hooks."""
import hashlib
import json
import re
from tree_sitter import Language, Parser
import tree_sitter_javascript

LANGUAGE = Language(tree_sitter_javascript.language())
SAFE_INT = 2**53 - 1


def decode_string(raw):
    # Legacy octal, identity escapes, lone surrogates and line continuations are skipped.
    if len(raw) < 2 or raw[0] not in ('"', "'") or raw[-1] != raw[0]:
        raise ValueError()
    text, output, i = raw[1:-1], [], 0
    mapping = {'n':'\n','r':'\r','t':'\t','b':'\b','f':'\f','v':'\v','\\':'\\',"'":"'",'"':'"'}
    while i < len(text):
        char = text[i]
        if char != '\\':
            output.append(char)
            i += 1
            continue
        i += 1
        if i >= len(text):
            raise ValueError()
        escape = text[i]
        if escape in mapping:
            output.append(mapping[escape]); i += 1
        elif escape in ('x','u'):
            length = 2 if escape == 'x' else 4
            digits = text[i+1:i+1+length]
            if not re.fullmatch('[0-9a-fA-F]{'+str(length)+'}', digits):
                raise ValueError()
            code = int(digits, 16)
            if 0xD800 <= code <= 0xDFFF:
                raise ValueError()
            output.append(chr(code)); i += length + 1
        elif escape == '0' and (i+1 == len(text) or not text[i+1].isdigit()):
            output.append('\0'); i += 1
        else:
            raise ValueError()
    return ''.join(output)


def integer(node, source):
    if node.type != 'number':
        raise ValueError()
    text = source[node.start_byte:node.end_byte].decode()
    if not re.fullmatch(r'(?:0|[1-9][0-9]*|0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+)', text):
        raise ValueError()
    number = int(text, 0) if text.lower().startswith(('0x','0b','0o')) else int(text)
    if number > SAFE_INT:
        raise ValueError()
    return number


def deobfuscate(code):
    parser = Parser(LANGUAGE)
    original = code.encode('utf-8')
    source, transformations = original, []
    initial = parser.parse(source)
    initial_errors = initial.root_node.has_error
    # Error recovery does not establish semantic regions; refuse the whole malformed input.
    if initial_errors:
        return {'code':code,'transformations':[], 'notes':['Sintaxis incompleta o inválida: no se modificó el archivo.']}
    for iteration in range(8):
        tree = parser.parse(source)
        edits = []

        def visit(node):
            if node.has_error:
                return
            replacement, rule = None, None
            raw = source[node.start_byte:node.end_byte].decode('utf-8')
            try:
                if node.type == 'binary_expression':
                    left, right = node.child_by_field_name('left'), node.child_by_field_name('right')
                    operator = node.child_by_field_name('operator')
                    op = source[operator.start_byte:operator.end_byte].decode() if operator else ''
                    # Comments inside an expression are preserved by skipping it.
                    if any(child.type == 'comment' for child in node.children):
                        raise ValueError()
                    if op == '+' and left.type == right.type == 'string':
                        if node.parent and node.parent.type == 'expression_statement':
                            raise ValueError()  # A concatenation must never become a use-strict directive.
                        value = decode_string(source[left.start_byte:left.end_byte].decode()) + decode_string(source[right.start_byte:right.end_byte].decode())
                        replacement, rule = json.dumps(value, ensure_ascii=True), 'Concatenación de cadenas literales'
                    elif op in ('+','-','*'):
                        a, b = integer(left, source), integer(right, source)
                        value = a+b if op == '+' else a-b if op == '-' else a*b
                        if abs(value) > SAFE_INT:
                            raise ValueError()
                        replacement, rule = str(value), 'Operación exacta entre enteros seguros'
                elif node.type == 'string' and '\\' in raw:
                    # Never turn an escaped string into a use-strict directive or alter directives.
                    parent = node.parent
                    if parent and parent.type == 'expression_statement':
                        raise ValueError()
                    replacement = json.dumps(decode_string(raw), ensure_ascii=True)
                    rule = 'Normalización de escapes de cadena'
            except (ValueError, AttributeError, UnicodeError):
                pass
            if replacement is not None and replacement != raw:
                edits.append((node.start_byte, node.end_byte, replacement.encode(), {'pass':iteration+1,'line':node.start_point.row+1,'rule':rule,'before':raw,'after':replacement}))
                return
            for child in node.named_children:
                visit(child)

        visit(tree.root_node)
        if not edits:
            break
        candidate = source
        for start, end, replacement, _record in reversed(edits):
            candidate = candidate[:start] + replacement + candidate[end:]
        if parser.parse(candidate).root_node.has_error:
            break
        source = candidate
        transformations.extend(edit[3] for edit in edits)
    return {'code':source.decode('utf-8'),'transformations':transformations,
            'original_sha256':hashlib.sha256(original).hexdigest(),
            'result_sha256':hashlib.sha256(source).hexdigest(),
            'notes':['Reglas estáticas conservadoras; no se ejecutó código. No recupera nombres originales ni cifrado dinámico.']}
