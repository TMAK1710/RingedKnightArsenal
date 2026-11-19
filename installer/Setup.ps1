param(
    [ValidateSet('Install','Uninstall','Verify')][string]$Action='Install',
    [string]$GamePath,
    [string]$PackageRoot=$PSScriptRoot
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Hash([string]$p) {
    $stream=[IO.File]::OpenRead($p);$algorithm=[Security.Cryptography.SHA256]::Create()
    try{return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','')}finally{$stream.Dispose();$algorithm.Dispose()}
}
function SafePath([string]$root,[string]$relative) {
    if([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)' -or $relative.Contains(':')){throw 'Invalid package path'}
    $root=[IO.Path]::GetFullPath($root).TrimEnd('\','/')
    $p=[IO.Path]::GetFullPath((Join-Path $root $relative))
    if(-not $p.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Path escapes destination'}
    $cursor=$p
    while($cursor.Length -gt $root.Length){
        if(Test-Path -LiteralPath $cursor){if((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw "Linked destination is not supported: $cursor"}}
        $cursor=Split-Path $cursor -Parent
    }
    return $p
}
function Put([string]$source,[string]$target){
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
    if((Hash $source) -ne (Hash $target)){throw "Copy verification failed: $target"}
}
function FindGame {
    $roots=@()
    foreach($key in @('HKCU:\Software\Valve\Steam','HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')){
        $entry=Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
        if($null -eq $entry){continue}
        foreach($name in @('SteamPath','InstallPath')){
            if($entry.PSObject.Properties.Name -contains $name){$roots+=([string]$entry.$name)}
        }
    }
    $libraries=@($roots)
    foreach($root in $roots){
        if($root -notmatch '^(?:[A-Za-z]:[\\/]|[\\/]{2})' -or -not [IO.Directory]::Exists($root)){continue}
        $vdf=[IO.Path]::Combine($root,'steamapps/libraryfolders.vdf')
        if(-not [IO.File]::Exists($vdf)){continue}
        try{$contents=[IO.File]::ReadAllText($vdf)}
        catch [IO.IOException]{continue}
        catch [UnauthorizedAccessException]{continue}
        foreach($match in [regex]::Matches($contents,'"path"\s+"([^"]+)"')){
            $libraries+=$match.Groups[1].Value.Replace('\\','\')
        }
    }
    # Steam can remember drives that are no longer mounted. Check them before joining paths.
    $found=@(foreach($library in $libraries){
        if($library -notmatch '^(?:[A-Za-z]:[\\/]|[\\/]{2})' -or -not [IO.Directory]::Exists($library)){continue}
        $game=[IO.Path]::Combine($library,'steamapps/common/PBZ')
        if([IO.File]::Exists([IO.Path]::Combine($game,'platform/steam/PBZ.exe'))){
            [IO.Path]::GetFullPath($game)
        }
    })
    $found=@($found | Sort-Object -Unique)
    if($found.Count -eq 1){return $found[0]}
    Add-Type -AssemblyName System.Windows.Forms
    $dialog=New-Object Windows.Forms.FolderBrowserDialog
    $dialog.Description='Select PBZ game root (contains ProjectPBZ and platform).'
    if($dialog.ShowDialog() -ne 'OK'){throw 'No game folder selected'}
    return $dialog.SelectedPath
}
if(-not $GamePath){$GamePath=FindGame}
$GamePath=[IO.Path]::GetFullPath($GamePath).TrimEnd('\','/')
$exe=SafePath $GamePath 'platform/steam/PBZ.exe'
if(-not(Test-Path -LiteralPath $exe)){throw 'Not a PBZ game root. Select the folder containing ProjectPBZ and platform.'}
if(@(Get-Process -Name PBZ,ProjectPBZ-Win64-Shipping -ErrorAction SilentlyContinue).Count){throw 'Close the game normally before setup. No files were changed.'}
$stateRoot=SafePath $GamePath 'RingedKnightArsenal-Backup'
$receiptPath=SafePath $stateRoot 'installed.json'
if($Action -eq 'Uninstall'){
    if(-not(Test-Path -LiteralPath $receiptPath)){throw 'No installation receipt found; nothing removed.'}
    $receipt=Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    $kept=0
    foreach($entry in @($receipt.Files)){
        if($entry.Kind -in @('Loader','Settings')){continue} # Shared loader stays available to other mods.
        $target=SafePath $GamePath $entry.Path
        if(Test-Path -LiteralPath $target){
            if((Hash $target) -ne $entry.InstalledHash){Write-Warning "Kept changed file: $($entry.Path)";$kept++;continue}
            if($entry.Backup){Put (SafePath $stateRoot $entry.Backup) $target}else{Remove-Item -LiteralPath $target}
        }elseif($entry.Backup){Put (SafePath $stateRoot $entry.Backup) $target}
    }
    if($kept){throw "Uninstall incomplete: $kept user-modified files preserved. Receipt retained for manual review."}
    Move-Item -LiteralPath $receiptPath -Destination (Join-Path $stateRoot ('uninstalled-'+[guid]::NewGuid().ToString('N')+'.json'))
    Write-Host 'Uninstalled. Previous files restored. Saves and backups retained.' -ForegroundColor Green
    return
}
$manifest=Get-Content -LiteralPath (Join-Path $PackageRoot 'manifest.json') -Raw | ConvertFrom-Json
if((Hash $exe) -ne $manifest.GameSHA256){throw 'Unsupported game executable. This package is pinned to Steam build 26367565; no files changed.'}
$files=@($manifest.Files)
if($files.Count -eq 0){throw 'Empty package'}
$proxyPath='platform/steam/dwmapi.dll'
$corePath='platform/steam/ue4ss/UE4SS.dll'
$proxyDiffers=$false
$seen=@{}
foreach($entry in $files){
    if($seen.ContainsKey($entry.Path)){throw 'Duplicate package destination'};$seen[$entry.Path]=$true
    $source=SafePath (Join-Path $PackageRoot 'payload') $entry.Path
    $target=SafePath $GamePath $entry.Path
    if((Hash $source) -ne $entry.SHA256){throw "Damaged package: $($entry.Path)"}
    if($entry.Kind -eq 'Loader' -and (Test-Path -LiteralPath $target) -and (Hash $target) -ne $entry.SHA256){
        if($entry.Path -eq $proxyPath){$proxyDiffers=$true;continue}
        if($entry.Path -eq $corePath){
            throw 'UE4SS core differs: platform/steam/ue4ss/UE4SS.dll. This mod requires the exact bundled core. No files changed. Use a separate clean game installation or check with the maintainer of your existing mods.'
        }
        throw "Different shared UE4SS file: $($entry.Path). No files changed."
    }
}
if($proxyDiffers){
    $core=SafePath $GamePath $corePath
    if(-not $seen.ContainsKey($corePath) -or -not [IO.File]::Exists($core)){
        throw 'A different dwmapi.dll exists, but the required platform/steam/ue4ss/UE4SS.dll is missing. No files changed. Identify the existing loader before replacing it.'
    }
    foreach($alternative in @('platform/steam/override.txt','platform/steam/UE4SS.dll')){
        if(Test-Path -LiteralPath (SafePath $GamePath $alternative)){
            throw "Existing loader may use a different UE4SS location ($alternative). No files changed. Check which UE4SS.dll the game loads."
        }
    }
    Write-Warning 'Existing dwmapi.dll differs, but the UE4SS core matches. Setup can preserve the existing dwmapi.dll.'
}
if($Action -eq 'Verify'){Write-Host "Verified $($files.Count) payload files and game compatibility.";return}
if(Test-Path -LiteralPath $receiptPath){
    $old=Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    if($old.PackageHash -eq (Hash (Join-Path $PackageRoot 'manifest.json'))){
        $ok=$true
        foreach($entry in $files){
            if($entry.Kind -eq 'Settings' -or ($proxyDiffers -and $entry.Path -eq $proxyPath)){continue}
            $t=SafePath $GamePath $entry.Path
            if(-not(Test-Path -LiteralPath $t) -or (Hash $t) -ne $entry.SHA256){$ok=$false;break}
        }
        if($ok){Write-Host 'This exact package is already installed.';return}
    }
    throw 'A managed installation already exists. Uninstall it first (backups are preserved), then install this package.'
}
if($proxyDiffers){
    Write-Host 'Continue only if your existing loader already starts UE4SS from platform/steam/ue4ss.'
    if((Read-Host 'Keep your current dwmapi.dll and install the mod? [y/N]') -ne 'y'){
        Write-Host 'Canceled. No files changed.'
        return
    }
}
$run='install-'+(Get-Date -Format yyyyMMdd-HHmmss)+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)
$session=SafePath $stateRoot $run
New-Item -ItemType Directory -Path $session -Force | Out-Null
# Save backups are never installed back automatically: they must not overwrite later progress.
$saveRoot=SafePath $GamePath 'ProjectPBZ/Saved/SaveGames'
if(Test-Path -LiteralPath $saveRoot){foreach($save in Get-ChildItem -LiteralPath $saveRoot -File -Recurse){
    $relative=$save.FullName.Substring($saveRoot.Length+1)
    $source=SafePath $saveRoot $relative
    Put $source (SafePath $session ('saves/'+$relative))
}}
$records=@();$touched=@()
try {
    foreach($entry in $files){
        $target=SafePath $GamePath $entry.Path
        # The existing loader and shared files are not owned by this mod.
        if($entry.Kind -eq 'Loader' -and (Test-Path -LiteralPath $target)){continue}
        if($entry.Kind -eq 'Settings' -and (Test-Path -LiteralPath $target)){continue}
        $backup=$null
        if(Test-Path -LiteralPath $target){$backup=$run+'/previous/'+$entry.Path;Put $target (SafePath $stateRoot $backup)}
        $record=[pscustomobject]@{Path=$entry.Path;InstalledHash=$entry.SHA256;Backup=$backup;Kind=$entry.Kind}
        $touched+=$record
        Put (SafePath (Join-Path $PackageRoot 'payload') $entry.Path) $target
        $records+=$record
    }
    [pscustomobject]@{Version=$manifest.Version;PackageHash=(Hash (Join-Path $PackageRoot 'manifest.json'));Files=@($records);SaveBackup=$run+'/saves'} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
}catch{
    $failure=$_
    [array]::Reverse($touched)
    foreach($entry in $touched){$target=SafePath $GamePath $entry.Path;if($entry.Backup){Put (SafePath $stateRoot $entry.Backup) $target}elseif(Test-Path -LiteralPath $target){Remove-Item -LiteralPath $target}}
    throw $failure
}
Write-Host 'Installed. Load a save; Ringed Knight Sword is added to the weapon bag automatically. Equip it manually.' -ForegroundColor Green
Write-Host "Backup: $session"
