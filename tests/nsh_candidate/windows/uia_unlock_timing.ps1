param([int]$ProcessId, [string]$Label)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$root = $A::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children,
  (New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, $ProcessId)))
function ById($id) { $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition($A::AutomationIdProperty, $id))) }
function Invoke($id) { (ById $id).GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
function Texts() { $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::Text))) | ForEach-Object { $_.Current.Name } }
$samples = @(
  @('sample-baseline', 'keex-synthetic-V41-VAULT'),
  @('sample-1000', 'keex-synthetic-M41-SCALE-1000-SMALL'),
  @('sample-10000', 'keex-synthetic-M41-SCALE-10000-SMALL'))
foreach ($round in 1..3) { foreach ($s in $samples) {
  Invoke $s[0]; Start-Sleep -Milliseconds 300
  (ById 'vault-password').GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($s[1])
  Start-Sleep -Milliseconds 300
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  Invoke 'unlock'
  $line = $null
  while ($sw.ElapsedMilliseconds -lt 60000) {
    $line = Texts | Where-Object { $_ -like ([string][char]0x8BA1 + [char]0x65F6 + '*') } | Select-Object -First 1
    if ($line) { break }
    Start-Sleep -Milliseconds 20
  }
  $ms = $sw.ElapsedMilliseconds
  $safe = if ($line) { ($line -replace '^\S+\s', '') } else { 'TIMEOUT' }
  "$Label round=$round sample=$($s[0]) unlock_to_visible_ms=$ms $safe"
} }
Invoke 'lock'
