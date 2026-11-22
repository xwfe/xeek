param([int]$Steps = 30, [string]$Key = '{TAB}')
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms
$A = [System.Windows.Automation.AutomationElement]
foreach ($i in 1..$Steps) {
  [System.Windows.Forms.SendKeys]::SendWait($Key); Start-Sleep -Milliseconds 150
  $f = $A::FocusedElement
  "{0,2} id={1} type={2} name={3} kbdFocusable={4}" -f $i, $f.Current.AutomationId, $f.Current.ControlType.ProgrammaticName, $f.Current.Name, $f.Current.IsKeyboardFocusable
}
