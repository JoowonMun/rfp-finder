<#
.SYNOPSIS
  rfp-finder 를 평일 아침마다 자동 실행하도록 Windows 작업 스케줄러에 등록/해제합니다.

.EXAMPLE
  .\register-task.ps1                 # 평일 08:30 등록
  .\register-task.ps1 -Time "07:50"   # 시간 지정
  .\register-task.ps1 -Unregister     # 해제
#>
param(
    [string]$Time = "08:30",
    [string]$WorkingDir = "",   # 기본: %USERPROFILE%\.rfp-finder (개발 중 .env 가 저장소에 있으면 그 폴더)
    [string]$Model = "sonnet",  # 무인 실행에 쓸 모델. 제안요청서 전문을 읽어 토큰이 많이 들므로 기본은 sonnet
    [switch]$Unregister
)

$TaskName = "rfp-finder"

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

$home_ = Join-Path $env:USERPROFILE ".rfp-finder"
$logs = Join-Path $home_ "logs"
New-Item -ItemType Directory -Force $logs | Out-Null
if (-not $WorkingDir) { $WorkingDir = $home_ }

# 무인 실행: python 실행(Bash/PowerShell 도구 모두), 파일 읽기/쓰기만 허용.
# 실행 폴더(runs) 가 있는 설정 폴더를 --add-dir 로 열어 줘야 분석 파일을 쓸 수 있다.
$prompt = "/rfp-finder 무인 실행입니다. 질문하지 말고 끝까지 진행한 뒤 결과를 요약하세요."
$allowed = "'Bash(python:*)' 'PowerShell(python:*)' 'Read' 'Write'"
$cmd = "`$log = Join-Path '$logs' ('scheduled-' + (Get-Date -Format yyyyMMdd) + '.log'); " +
       "Set-Location '$WorkingDir'; " +
       "& '$claude' -p '$prompt' --model '$Model' --add-dir '$home_' --allowedTools $allowed *>> `$log"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $WorkingDir `
    -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$cmd`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Output "등록 완료: 평일 $Time 에 '$TaskName' 실행. 로그: $logs"
Write-Output "지금 한 번 시험 실행: Start-ScheduledTask -TaskName $TaskName"
