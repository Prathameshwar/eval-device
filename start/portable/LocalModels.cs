using System;
using System.Diagnostics;
using System.IO;
using System.Text;

// The manager, detached daemon and installers share this private Python runtime.
class LocalModels {
    static void RepairEnvironment(string root, string capability, string scripts) {
        string cfg = Path.Combine(root, "local-models", ".runtime", "environments", capability, "pyvenv.cfg");
        if (!File.Exists(cfg)) return;
        string home = "home = " + scripts;
        string[] lines = File.ReadAllLines(cfg);
        bool found = false;
        for (int i = 0; i < lines.Length; i++) {
            if (lines[i].StartsWith("home = ", StringComparison.OrdinalIgnoreCase)) {
                found = true;
                lines[i] = home;
            }
        }
        if (!found) throw new IOException("Bundled runtime has no Python home");
        File.WriteAllLines(cfg, lines);
    }
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
            string scripts = Path.Combine(root, "local-models", ".venv", "Scripts");
            string python = Path.Combine(scripts, "python.exe");
            string uv = Path.Combine(root, "tools", "uv.exe");
            bool check = args.Length == 1 && args[0] == "--self-test";
            string script = check ? Path.Combine(root, "start", "local_models_check.py") : Path.Combine(root, "local-models", "manage_local_models.py");
            if (!File.Exists(python) || !File.Exists(uv) || !File.Exists(script))
                throw new IOException("Extract the complete Local Models folder before running this executable.");
            RepairEnvironment(root, "asr", scripts);
            RepairEnvironment(root, "tts", scripts);
            var command = new StringBuilder("-B -X utf8 " + Quote(script));
            if (!check) foreach (string arg in args) command.Append(" ").Append(Quote(arg));
            // Some Windows parents pass both Path and PATH. The .NET Framework
            // process environment table rejects that duplicate case-insensitively.
            string inheritedPath = Environment.GetEnvironmentVariable("PATH") ?? "";
            Environment.SetEnvironmentVariable("Path", null);
            Environment.SetEnvironmentVariable("PATH", null);
            Environment.SetEnvironmentVariable("Path", Path.Combine(root, "tools") + ";" + scripts + ";" + inheritedPath);
            var info = new ProcessStartInfo(python, command.ToString());
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.EnvironmentVariables.Remove("PYTHONHOME");
            info.EnvironmentVariables.Remove("PYTHONPATH");
            info.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            info.EnvironmentVariables["UV_PYTHON_DOWNLOADS"] = "never";
            using (var process = Process.Start(info)) {
                process.WaitForExit();
                return process.ExitCode;
            }
        } catch (Exception) {
            Console.Error.WriteLine("Cannot start Local Models. Extract the whole package to a writable local folder and retry.");
            return 1;
        }
    }
}
