using System;
using System.IO;

namespace VRClassroom
{
    /// <summary>
    /// Cheap process resource snapshot for logs (resident memory, open file
    /// descriptors, managed heap). Used to spot slow leaks that only show up after
    /// a long class session: if rssMB/fds keep growing with every opened video,
    /// something is not being released. Reads /proc, so values are -1 off Android/Linux.
    /// </summary>
    public static class ProcessDiagnostics
    {
        public static string Snapshot()
        {
            long managedMb = GC.GetTotalMemory(false) / (1024 * 1024);
            return $"rssMB={ReadRssMb()}, fds={CountOpenFds()}, managedMB={managedMb}";
        }

        private static long ReadRssMb()
        {
            try
            {
                foreach (string line in File.ReadAllLines("/proc/self/status"))
                {
                    if (!line.StartsWith("VmRSS:", StringComparison.Ordinal)) continue;
                    string[] parts = line.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                    if (parts.Length >= 2 && long.TryParse(parts[1], out long kb))
                        return kb / 1024;
                }
            }
            catch
            {
                // not available on this platform
            }
            return -1;
        }

        private static int CountOpenFds()
        {
            try
            {
                return Directory.GetFileSystemEntries("/proc/self/fd").Length;
            }
            catch
            {
                return -1;
            }
        }
    }
}
