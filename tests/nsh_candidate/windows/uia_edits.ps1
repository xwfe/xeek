param([int]$ProcessId)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$root = $A::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children,
  (New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, $ProcessId)))
"window class=$($root.Current.ClassName) framework=$($root.Current.FrameworkId)"
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$all | Group-Object { $_.Current.ControlType.ProgrammaticName } | ForEach-Object { "count $($_.Name)=$($_.Count)" }
$all | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Edit } | ForEach-Object {
  $c = $_.Current
  $pats = ($_.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName }) -join ','
  "edit id=$($c.AutomationId) name='$($c.Name)' help='$($c.HelpText)' isPassword=$($c.IsPassword) enabled=$($c.IsEnabled) patterns=$pats"
}
$b = $all | Where-Object { $_.Current.AutomationId -eq 'unlock' }
"button unlock patterns=" + (($b.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName }) -join ',')
