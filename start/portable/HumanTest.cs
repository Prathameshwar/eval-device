using System;
using System.Diagnostics;
using System.IO;
using System.Text;

// Uses the Windows .NET Framework; Python and all application libraries are private.
class HumanTest {
    static string Quote(string value) {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') result.Append('\\', slashes * 2 + 1);
            else result.Append('\\', slashes);
            result.Append(c); slashes = 0;
        }
        return result.Append('\\', slashes * 2).Append('"').ToString();
    }
    static int Main(string[] args) {
        try {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(root, "human-test", ".venv", "Scripts", "python.exe");
            bool check = args.Length == 1 && args[0] == "--self-test";
            string script = Path.Combine(root, "start", check ? "portable_check.py" : "launch.py");
            if (!File.Exists(python) || !File.Exists(script))
                throw new IOException("Extract the complete Human-test folder before running this executable.");
            var command = new StringBuilder("-B -X utf8 " + Quote(script));
            if (!check) foreach (string arg in args) command.Append(" ").Append(Quote(arg));
            var info = new ProcessStartInfo(python, command.ToString());
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            // ProcessStartInfo.EnvironmentVariables fails when Windows inherited both
            // PATH and Path. Sanitize this short-lived launcher before spawning Python.
            Environment.SetEnvironmentVariable("PYTHONHOME", null);
            Environment.SetEnvironmentVariable("PYTHONPATH", null);
            Environment.SetEnvironmentVariable("PYTHONNOUSERSITE", "1");
            using (var process = Process.Start(info)) {
                process.WaitForExit();
                return process.ExitCode;
            }
        } catch (Exception) {
            Console.Error.WriteLine("Cannot start Human-test. Extract the whole package to a writable local folder and retry.");
            return 1;
        }
    }
}
