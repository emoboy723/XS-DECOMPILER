// Static Ghidra post-analysis script. Does not execute the imported program.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
public class StrataExport extends GhidraScript {
    public void run() throws Exception {
        DecompInterface engine = new DecompInterface();
        try {
            engine.openProgram(currentProgram);
            try (PrintWriter writer = new PrintWriter(getScriptArgs()[0], StandardCharsets.UTF_8)) {
                writer.println("/* Ghidra recovered pseudocode; not original source. */");
                FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
                while (functions.hasNext() && !monitor.isCancelled()) {
                    Function fn = functions.next();
                    if (fn.isExternal()) continue;
                    DecompileResults result = engine.decompileFunction(fn, 30, monitor);
                    writer.println("\n/* " + fn.getName() + " @ " + fn.getEntryPoint() + " */");
                    if (result.decompileCompleted()) writer.println(result.getDecompiledFunction().getC());
                    else writer.println("/* Could not decompile this function. */");
                }
            }
        } finally { engine.dispose(); }
    }
}
