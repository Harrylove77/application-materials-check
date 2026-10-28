param(
    [Parameter(Mandatory=$true)][string]$InputFile,
    [Parameter(Mandatory=$true)][string]$OutputFile
)
$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $InputFile).Path
if ([IO.Path]::GetExtension($sourcePath).ToLowerInvariant() -ne '.docx') {
    throw 'Only .docx is supported; do not run macros or legacy documents.'
}
$destinationPath = [IO.Path]::GetFullPath($OutputFile)
if ([IO.Path]::GetExtension($destinationPath).ToLowerInvariant() -ne '.pdf') {
    throw 'Output must end in .pdf.'
}
if (Test-Path -LiteralPath $destinationPath) { throw 'Refusing to overwrite an existing file.' }
if (-not (Test-Path -LiteralPath (Split-Path -Parent $destinationPath) -PathType Container)) {
    throw 'Output parent directory must exist.'
}
$wordApp = $null
$wordDocument = $null
try {
    $wordApp = New-Object -ComObject Word.Application
    $wordApp.Visible = $false
    $wordApp.DisplayAlerts = 0
    $wordApp.AutomationSecurity = 3
    $wordApp.Options.UpdateLinksAtOpen = $false
    $wordDocument = $wordApp.Documents.Open($sourcePath, $false, $true, $false)
    if ($wordDocument.Revisions.Count -gt 0 -or $wordDocument.Comments.Count -gt 0) {
        throw 'Tracked changes/comments found. Resolve a copy with the student before final export.'
    }
    $wordDocument.ExportAsFixedFormat($destinationPath, 17)
    if (-not (Test-Path -LiteralPath $destinationPath -PathType Leaf)) {
        throw 'Word did not create the PDF.'
    }
    Write-Output $destinationPath
}
finally {
    if ($null -ne $wordDocument) {
        $wordDocument.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordDocument)
    }
    if ($null -ne $wordApp) {
        $wordApp.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordApp)
    }
}

