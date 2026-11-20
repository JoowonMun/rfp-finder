<#
.SYNOPSIS
  g2b-rfp-scout 를 평일 아침마다 자동 실행하도록 Windows 작업 스케줄러에 등록/해제합니다.

.EXAMPLE
  .\register-task.ps1                 # 평일 08:30 등록
  .\register-task.ps1 -Time "07:50"   # 시간 지정
  .\register-task.ps1 -Unregister     # 해제
#>
param(
    [string]$Time = "08:30",
    [switch]$Unregister
)

$TaskName = "g2b-rfp-scout"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "작업 '$TaskName' 을(를) 해제했습니다."
    return
}

$claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $claude) {
    Write-Error "claude 명령을 찾을 수 없습니다. Claude Code CLI 설치 후 다시 실행하세요."
    return
}

$home_ = Join-Path $env:USERPROFILE ".g2b-rfp-scout"
$logs = Join-Path $home_ "logs"
New-Item -ItemType Directory -Force $logs | Out-Null

# 무인 실행: 스크립트 실행(python), 파일 읽기/쓰기만 허용
$prompt = "/g2b-rfp-scout 무인 실행입니다. 질문하지 말고 끝까지 진행한 뒤 결과를 요약하세요."
$allowed = "'Bash(python:*)' 'Read' 'Write'"
$cmd = "`$log = Join-Path '$logs' ('scheduled-' + (Get-Date -Format yyyyMMdd) + '.log'); " +
       "Set-Location '$WorkingDir'; " +
       "& '$claude' -p '$prompt' --allowedTools $allowed *>> `$log"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$cmd`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Output "등록 완료: 평일 $Time 에 '$TaskName' 실행. 로그: $logs"
Write-Output "지금 한 번 시험 실행: Start-ScheduledTask -TaskName $TaskName"
