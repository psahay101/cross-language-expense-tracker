param(
    [string]$RepositoryUrl = 'REPOSITORY_URL_PENDING',
    [switch]$ReportsOnly,
    [switch]$SkipScreenshots,
    [string]$PythonExecutable = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$docsRoot = Join-Path $projectRoot 'docs'

function Read-JsonFile([string]$Path) {
    $parsed = [System.IO.File]::ReadAllText($Path) | ConvertFrom-Json
    if ($parsed -is [System.Array]) {
        foreach ($item in $parsed) { Write-Output $item }
    } else { Write-Output $parsed }
}

function Resolve-Content([string]$Text) {
    return $Text.Replace('REPOSITORY_URL_PENDING', $RepositoryUrl)
}

if (-not $PythonExecutable) {
    $portablePython = Join-Path (Split-Path -Parent $projectRoot) '.tools\python\python.exe'
    $PythonExecutable = if (Test-Path -LiteralPath $portablePython) { $portablePython } else { 'python' }
}

if (-not $SkipScreenshots) {
    $chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if (-not (Test-Path -LiteralPath $chrome)) { throw 'Chrome is required to render recorded-output screenshots.' }
    $profile = Join-Path (Split-Path -Parent $projectRoot) '.tools\project-chrome-profile'
    foreach ($name in @('python_demo', 'cpp_demo', 'parity_tests')) {
        $htmlPath = Join-Path $docsRoot ('evidence\' + $name + '.html')
        $pngPath = Join-Path $docsRoot ('screenshots\' + $name + '.png')
        $uri = [System.Uri]::new($htmlPath).AbsoluteUri
        $arguments = @('--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', ('--user-data-dir=' + $profile), '--hide-scrollbars', '--window-size=1200,750', ('--screenshot=' + $pngPath), $uri)
        $chromeErrorLog = Join-Path (Split-Path -Parent $projectRoot) ('.tools\chrome-' + $name + '.stderr.txt')
        [void](Start-Process -FilePath $chrome -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait -RedirectStandardError $chromeErrorLog)
        if (-not (Test-Path -LiteralPath $pngPath)) { throw ('Missing screenshot: ' + $name) }
        Write-Output ('Rendered screenshot: ' + $name)
    }
}

& $PythonExecutable (Join-Path $PSScriptRoot 'build_reports.py') --repository-url $RepositoryUrl
if ($LASTEXITCODE -ne 0) { throw 'Report package builder failed.' }

$word = $null
$document = $null
$reportResults = @()
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.ScreenUpdating = $false
    $reportSpecifications = @(Read-JsonFile (Join-Path $docsRoot 'report_content.json')) + @(Read-JsonFile (Join-Path $docsRoot 'comparison_content.json'))
    foreach ($specification in $reportSpecifications) {
        $docxPath = Join-Path $docsRoot $specification.filename
        $pdfPath = [System.IO.Path]::ChangeExtension($docxPath, '.pdf')
        Write-Output ('Opening package in Word: ' + $specification.filename)
        $missing = [System.Type]::Missing
        $document = $word.Documents.Open($docxPath, $false, $false, $false, $missing, $missing, $false, $missing, $missing, $missing, $missing, $false, $false)
        $document.Repaginate()
        $pages = $document.ComputeStatistics(2)
        $document.Save()
        $document.ExportAsFixedFormat($pdfPath, 17)
        $document.Close(0)
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
        $document = $null
        $check = $word.Documents.Open($docxPath, $false, $true, $false, $missing, $missing, $false, $missing, $missing, $missing, $missing, $false, $false)
        $check.Close(0)
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($check)
        $reportResults += [pscustomobject]@{ File = $specification.filename; Pages = $pages; OpenedWithoutRepair = $true }
        Write-Output ('Generated and verified: ' + $specification.filename + ' (' + $pages + ' pages)')
    }
} finally {
    if ($document) { try { $document.Close(0) } catch {}; [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) }
    if ($word) { try { $word.Quit(0) } catch {}; [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

function Color-Rgb([int]$Red, [int]$Green, [int]$Blue) {
    return $Red + 256 * $Green + 65536 * $Blue
}

function Add-SlideText {
    param($Slide, [string]$Text, [double]$Left, [double]$Top, [double]$Width, [double]$Height,
          [double]$Size = 23, [bool]$Bold = $false, [int]$Color = 0, [string]$Font = 'Aptos')
    $shape = $Slide.Shapes.AddTextbox(1, $Left, $Top, $Width, $Height)
    $shape.TextFrame.MarginLeft = 0
    $shape.TextFrame.MarginRight = 0
    $shape.TextFrame.MarginTop = 0
    $shape.TextFrame.MarginBottom = 0
    $shape.TextFrame.WordWrap = -1
    $shape.TextFrame.TextRange.Text = Resolve-Content $Text
    $shape.TextFrame.TextRange.Font.Name = $Font
    $shape.TextFrame.TextRange.Font.Size = $Size
    $shape.TextFrame.TextRange.Font.Bold = if ($Bold) { -1 } else { 0 }
    $shape.TextFrame.TextRange.Font.Color.RGB = $Color
    $shape.TextFrame.TextRange.ParagraphFormat.SpaceAfter = 10
    if ($Font -eq 'Consolas') { $shape.TextFrame.TextRange.ParagraphFormat.SpaceAfter = 0 }
    $minimumSize = if ($Font -eq 'Consolas') { 11 } elseif ($Size -le 15) { $Size } elseif ($Size -ge 28) { 22 } else { 18 }
    while ($shape.TextFrame.TextRange.BoundHeight -gt $Height -and $shape.TextFrame.TextRange.Font.Size -gt $minimumSize) {
        $shape.TextFrame.TextRange.Font.Size -= 0.5
    }
    return $shape
}

if (-not $ReportsOnly) {
    $powerpoint = $null
    $presentation = $null
    try {
        $slideSpecification = Read-JsonFile (Join-Path $docsRoot 'presentation_content.json')
        $powerpoint = New-Object -ComObject PowerPoint.Application
        $presentation = $powerpoint.Presentations.Add(0)
        $presentation.PageSetup.SlideWidth = 960
        $presentation.PageSetup.SlideHeight = 540
        $navy = Color-Rgb 21 40 62
        $teal = Color-Rgb 0 121 131
        $gray = Color-Rgb 81 94 108
        $pale = Color-Rgb 242 246 250
        $white = Color-Rgb 255 255 255
        for ($index = 0; $index -lt $slideSpecification.slides.Count; $index++) {
            $item = $slideSpecification.slides[$index]
            $slide = $presentation.Slides.Add($index + 1, 12)
            $slide.Background.Fill.ForeColor.RGB = $white
            $accent = $slide.Shapes.AddShape(1, 0, 0, 960, 10)
            $accent.Fill.ForeColor.RGB = $teal
            $accent.Line.Visible = 0
            [void](Add-SlideText -Slide $slide -Text $item.title -Left 40 -Top 28 -Width 880 -Height 62 -Size 29 -Bold $true -Color $navy)
            $minutes = [Math]::Round($item.duration_seconds / 60.0, 2)
            [void](Add-SlideText -Slide $slide -Text ($item.speaker + ' | ' + $minutes + ' min') -Left 40 -Top 91 -Width 880 -Height 24 -Size 12 -Color $gray)
            if ($item.image) {
                $imagePath = Join-Path $projectRoot $item.image
                $picture = $slide.Shapes.AddPicture($imagePath, 0, -1, 38, 130)
                $picture.LockAspectRatio = -1
                $picture.Height = 355
                if ($picture.Width -gt 640) { $picture.Width = 640 }
                $picture.Left = 40
                $picture.Top = 134
                $bulletText = $item.bullets -join ([string][char]13 + [string][char]13)
                [void](Add-SlideText -Slide $slide -Text $bulletText -Left 665 -Top 145 -Width 255 -Height 320 -Size 19 -Color $navy)
            } elseif ($item.codeBlocks -and $item.codeBlocks.Count -gt 0) {
                $bulletText = $item.bullets -join ' • '
                [void](Add-SlideText -Slide $slide -Text $bulletText -Left 40 -Top 131 -Width 880 -Height 86 -Size 19 -Color $gray)
                $count = $item.codeBlocks.Count
                $longestLine = 0
                foreach ($codeBlock in $item.codeBlocks) {
                    foreach ($line in [regex]::Split($codeBlock.code, '\r?\n')) { $longestLine = [Math]::Max($longestLine, $line.Length) }
                }
                $stacked = $count -gt 1 -and $longestLine -gt 47
                $panelWidth = if ($count -gt 1) { 428 } else { 880 }
                if ($stacked) { $panelWidth = 880 }
                $nextPanelTop = 222
                for ($blockIndex = 0; $blockIndex -lt $count; $blockIndex++) {
                    $left = if ($stacked) { 40 } else { 40 + $blockIndex * 452 }
                    $lineCount = [regex]::Split($item.codeBlocks[$blockIndex].code, '\r?\n').Count
                    $panelTop = if ($stacked) { $nextPanelTop } else { 229 }
                    $panelHeight = if ($stacked) { 31 + 15.2 * $lineCount } else { 249 }
                    $panel = $slide.Shapes.AddShape(1, $left, $panelTop, $panelWidth, $panelHeight)
                    $panel.Fill.ForeColor.RGB = $pale
                    $panel.Line.Visible = 0
                    $labelTop = $panelTop + 8
                    $labelHeight = if ($stacked) { 18 } else { 31 }
                    $codeTop = if ($stacked) { $panelTop + 29 } else { 281 }
                    $codeHeight = if ($stacked) { $panelHeight - 31 } else { 184 }
                    $codeSize = if ($stacked) { 12.5 } else { 14 }
                    [void](Add-SlideText -Slide $slide -Text $item.codeBlocks[$blockIndex].label -Left ($left + 15) -Top $labelTop -Width ($panelWidth - 30) -Height $labelHeight -Size 13 -Bold $true -Color $teal)
                    [void](Add-SlideText -Slide $slide -Text $item.codeBlocks[$blockIndex].code -Left ($left + 15) -Top $codeTop -Width ($panelWidth - 30) -Height $codeHeight -Size $codeSize -Color $navy -Font 'Consolas')
                    if ($stacked) { $nextPanelTop += $panelHeight + 5 }
                }
            } else {
                $bulletText = $item.bullets -join ([string][char]13 + [string][char]13)
                [void](Add-SlideText -Slide $slide -Text $bulletText -Left 55 -Top 151 -Width 850 -Height 327 -Size 25 -Color $navy)
            }
            $footer = 'Expense Tracker | Python + C++17 | MSCS632'
            [void](Add-SlideText -Slide $slide -Text $footer -Left 40 -Top 512 -Width 780 -Height 18 -Size 10 -Color $gray)
            [void](Add-SlideText -Slide $slide -Text (($index + 1).ToString() + ' / ' + $slideSpecification.slides.Count) -Left 859 -Top 508 -Width 66 -Height 22 -Size 12 -Color $gray)
            $notesText = 'Speaker: ' + $item.speaker + '. Planned time: ' + $item.duration_seconds + ' seconds.' + [string][char]13 + [string][char]13 + (Resolve-Content $item.notes)
            $notesWritten = $false
            foreach ($placeholder in $slide.NotesPage.Shapes.Placeholders) {
                if ($placeholder.PlaceholderFormat.Type -eq 2) {
                    $placeholder.TextFrame.TextRange.Text = $notesText
                    $notesWritten = $true
                    break
                }
            }
            if (-not $notesWritten) { throw ('Could not attach speaker notes to slide ' + ($index + 1)) }
        }
        $pptxPath = Join-Path $docsRoot 'Deliverable 3 - Presentation.pptx'
        $slidesPdfPath = Join-Path $docsRoot 'Deliverable 3 - Presentation.pdf'
        $presentation.SaveAs($pptxPath, 24)
        $presentation.SaveAs($slidesPdfPath, 32)
        $presentation.SaveAs($pptxPath, 24)
        $exportRoot = Join-Path $docsRoot 'slide_previews'
        [void][System.IO.Directory]::CreateDirectory($exportRoot)
        foreach ($slideNumber in @(1, 5, 7, 10, 13, $presentation.Slides.Count)) {
            $presentation.Slides.Item($slideNumber).Export((Join-Path $exportRoot ('slide-' + $slideNumber + '.png')), 'PNG', 1600, 900)
        }
        $slideCount = $presentation.Slides.Count
        $presentation.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation)
        $presentation = $null
        $check = $powerpoint.Presentations.Open($pptxPath, -1, 0, 0)
        if ($check.Slides.Count -ne $slideCount) { throw 'PowerPoint verification found a different slide count.' }
        $check.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($check)
        Write-Output ('Generated and verified presentation: ' + $slideCount + ' slides')
    } finally {
        if ($presentation) { try { $presentation.Close() } catch {}; [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation) }
        if ($powerpoint) { try { $powerpoint.Quit() } catch {}; [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($powerpoint) }
        [System.GC]::Collect()
        [System.GC]::WaitForPendingFinalizers()
    }
}

$reportResults | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $docsRoot 'document_verification.json') -Encoding UTF8
