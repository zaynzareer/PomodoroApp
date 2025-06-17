AppNames = { 
    # Add more app names as needed
    "explorer.exe": "Windows Explorer",
    "taskmgr.exe": "Task Manager",    
    "powershell.exe": "Windows PowerShell",
    "cmd.exe": "Command Prompt",  
    "WindowsTerminal.exe": "Windows Terminal",
    "ShellExperienceHost.exe": "Windows Shell Experience Host",
    "msedgewebview2.exe": "Microsoft Edge WebView2",
    "code.exe": "Visual Studio Code",
    "neutralino-win_x64.exe": "Neutralino App",
    "opera.exe": "Opera Browser",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Mozilla Firefox",
    "winword.exe": "Microsoft Word",
    "excel.exe": "Microsoft Excel",
    "powerpnt.exe": "Microsoft PowerPoint",
    "vlc.exe": "VLC Media Player",
    "notepad.exe": "Notepad",
}

def get_app_name(exe_name):
    return AppNames.get(exe_name.lower(), exe_name)