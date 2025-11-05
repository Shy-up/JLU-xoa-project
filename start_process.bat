@echo off
setlocal

:: Define the absolute path for Python and PowerShell Script
set PYTHON_EXE="C:\Users\wangz\AppData\Local\Programs\Python\Python313\python.exe" 
set PS_DIALOG_SCRIPT="D:\Project\jlu-xoa-project\confirm_dialog.ps1"
set DR_EXE="D:\Program Files (x86)\Drcom\DrUpdateClient\DrMain.exe"
set SCRIPT_1="D:\Project\jlu-xoa-project\get_data_from_oa.py"
set SCRIPT_2="D:\Project\jlu-xoa-project\update_db.py"
set SCRIPT_3="D:\Project\jlu-xoa-project\app.py"
set TARGET_HTML="http://127.0.0.1:5000/oa"
set SCRIPT_FOLDER="D:\Project\jlu-xoa-project\"

:: ----------------------------------------------------
:: Step 1: Start the main EXE program
echo Starting DrMain.exe...
start "" %DR_EXE%

:: Step 2: Call PowerShell to show confirmation dialog
echo Showing dialog...
PowerShell.exe -ExecutionPolicy Bypass -File %PS_DIALOG_SCRIPT%

:: Step 3: Check the Exit Code (0 for Yes, any other code for No/Error)
if %ERRORLEVEL% equ 0 goto EXECUTE_TASKS

:: If ERRORLEVEL is not 0 (User clicked No or PowerShell crashed)
goto CANCEL_TASKS


:: --- EXECUTION BLOCK ---
:EXECUTE_TASKS
    echo Task confirmed.
    
    :: Pause for 1 second to give user a chance to read the confirmation
    ping 127.0.0.1 -n 2 > nul
    
    :: Forced CD to fix relative paths
    cd /d %SCRIPT_FOLDER%

    :: Step 4: Execute blocking scripts (Data Fetch and DB Update)
    
    echo Running script 1 (Data Fetch)...
    call %PYTHON_EXE% %SCRIPT_1%
    
    echo Running script 2 (DB Update)...
    call %PYTHON_EXE% %SCRIPT_2%
    
    echo Starting script 3 (Server)...
    start "Python Server" %PYTHON_EXE% %SCRIPT_3%
    

    echo Giving server 2 seconds to initialize...
    ping 127.0.0.1 -n 3 > nul 
    

    echo Opening HTML page...
    start "" %TARGET_HTML%
    
    goto FINAL_EXIT_PAUSE


:: --- CANCELLATION BLOCK ---
:CANCEL_TASKS
    echo Task cancelled or failed.
    goto FINAL_EXIT_PAUSE


:: --- FINAL EXIT ---
:FINAL_EXIT_PAUSE
    :: Final pause before exit, ensures all errors are visible
    pause
    endlocal
    exit
