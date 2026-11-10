using System;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

/// <summary>
/// Command-line Quest build:
///   Unity.exe -batchmode -quit -projectPath VRClassroomPlayer -executeMethod BuildPlayerCli.BuildQuest [-buildOutput path.apk]
/// Default output: Builds/VRClassroomPlayer-Quest.apk (the path the dashboard's "Player APK path" points to).
/// </summary>
public static class BuildPlayerCli
{
    public static void BuildQuest()
    {
        string[] args = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(args, "-buildOutput");
        string output = i >= 0 && i + 1 < args.Length ? args[i + 1] : "Builds/VRClassroomPlayer-Quest.apk";

        string[] scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
        BuildReport report = BuildPipeline.BuildPlayer(scenes, output, BuildTarget.Android, BuildOptions.None);
        Debug.Log($"[BuildPlayerCli] {report.summary.result}: {output}");
        EditorApplication.Exit(report.summary.result == BuildResult.Succeeded ? 0 : 1);
    }
}
