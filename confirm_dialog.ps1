# PowerShell 脚本：创建带“是/否”按钮的对话框
Add-Type -AssemblyName System.Windows.Forms
$result = [System.Windows.Forms.MessageBox]::Show('要执行3个Python脚本并打开网页吗？', '任务确认', 'YesNo', 'Question')

# 根据用户的点击设置退出代码
# Yes 返回 0
# No 返回 1
if ($result -eq 'Yes') {
    exit 0
} else {
    exit 1
}