using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class MusicCleanerLauncher
{
    [STAThread]
    private static void Main()
    {
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        string launch = Path.Combine(folder, "run_windows.bat");
        if (!File.Exists(launch))
        {
            MessageBox.Show("Extract the entire ZIP first. Keep MusicCleaner.exe beside run_windows.bat.",
                "Music Cleaner", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = launch,
                WorkingDirectory = folder,
                UseShellExecute = true
            });
        }
        catch (Exception error)
        {
            MessageBox.Show("Could not start Music Cleaner: " + error.Message,
                "Music Cleaner", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
