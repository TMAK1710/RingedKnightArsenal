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
    $temporary=$target+'.rka-'+[guid]::NewGuid().ToString('N')+'.tmp'
    try{
        [IO.File]::Copy($source,$temporary)
        if((Hash $source) -ne (Hash $temporary)){throw "Copy verification failed: $target"}
        if([IO.File]::Exists($target)){[IO.File]::Replace($temporary,$target,[NullString]::Value)}
        else{[IO.File]::Move($temporary,$target)}
    }finally{
        if([IO.File]::Exists($temporary)){[IO.File]::Delete($temporary)}
    }
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
    $entries=@($receipt.Files)
    [array]::Reverse($entries)
    $restore=@(foreach($entry in $entries){
        if($entry.Kind -in @('Loader','Settings')){continue} # Shared loader stays available to other mods.
        $target=SafePath $GamePath $entry.Path
        $backup=$null
        if($entry.Backup){
            $backup=SafePath $stateRoot $entry.Backup
            $backupHash=Hash $backup
            if($entry.PSObject.Properties['BackupHash'] -and $entry.BackupHash -ne $backupHash){throw "Damaged backup: $($entry.Path). Nothing removed."}
        }
        if(Test-Path -LiteralPath $target){
            $currentHash=Hash $target
            if($backup -and $currentHash -eq $backupHash){continue} # Can resume an interrupted uninstall.
            if($currentHash -ne $entry.InstalledHash){throw "File changed after installation: $($entry.Path). Nothing removed. Back up the change before trying again."}
        }elseif(-not $backup){continue}
        [pscustomobject]@{Target=$target;Backup=$backup}
    })
    foreach($file in $restore){
        if($file.Backup){Put $file.Backup $file.Target}
        else{[IO.File]::Delete($file.Target)}
    }
    Move-Item -LiteralPath $receiptPath -Destination (Join-Path $stateRoot ('uninstalled-'+[guid]::NewGuid().ToString('N')+'.json'))
    Write-Host 'Uninstalled. Previous files restored. Saves and backups retained.' -ForegroundColor Green
    return
}
$manifestPath=Join-Path $PackageRoot 'manifest.json'
if(-not [IO.File]::Exists($manifestPath)){throw 'manifest.json is missing. Extract the complete installation ZIP before running setup.'}
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if((Hash $exe) -ne $manifest.GameSHA256){throw 'Unsupported game executable. This package is pinned to Steam build 26367565; no files changed.'}
$files=@($manifest.Files)
if($files.Count -eq 0){throw 'Empty package'}
$proxyPath='platform/steam/dwmapi.dll'
$corePath='platform/steam/ue4ss/UE4SS.dll'
$ue4ssPrefix='platform/steam/ue4ss/'
$overridePath='platform/steam/override.txt'
$overrideFile=SafePath $GamePath $overridePath
$loaderConflicts=@()
$sources=@{}
$seen=@{}
foreach($entry in $files){
    $key=$entry.Path.Replace('\','/')
    if($seen.ContainsKey($key)){throw 'Duplicate package destination'};$seen[$key]=$true
    $source=SafePath (Join-Path $PackageRoot 'payload') $entry.Path
    $target=SafePath $GamePath $entry.Path
    if((Hash $source) -ne $entry.SHA256){throw "Damaged package: $($entry.Path)"}
    $sources[$entry.Path]=$source
    if($key -eq ($ue4ssPrefix+'LICENSE')){continue}
    if(($entry.Kind -eq 'Loader' -or $key -eq ($ue4ssPrefix+'MemberVariableLayout.ini')) -and
            (Test-Path -LiteralPath $target) -and (Hash $target) -ne $entry.SHA256){
        $loaderConflicts+=$entry.Path
    }
}
foreach($alternative in @($overridePath,'platform/steam/UE4SS.dll','platform/steam/Mods')){
    if(Test-Path -LiteralPath (SafePath $GamePath $alternative)){$loaderConflicts+=$alternative}
}
$settings=SafePath $GamePath ($ue4ssPrefix+'UE4SS-settings.ini')
if([IO.File]::Exists($settings) -and [IO.File]::ReadAllText($settings) -match '(?im)^[ \t]*(?:ModsFolderPath|[+-]ModsFolderPaths)[ \t]*=[ \t]*[^\s;#]'){
    $loaderConflicts+='custom UE4SS mod folders'
}
$useSeparateLoader=$loaderConflicts.Count -gt 0
if($useSeparateLoader){
    if(-not $seen.ContainsKey($proxyPath) -or -not $seen.ContainsKey($corePath)){
        throw 'Existing UE4SS differs and the package is missing the bundled loader. Extract the complete installation ZIP.'
    }
    Write-Host ('Existing UE4SS configuration detected: '+($loaderConflicts -join ', '))
    Write-Host 'Setup will use a separate UE4SS folder. Other UE4SS mods in the original folder are paused until uninstall.'
}
if($Action -eq 'Verify'){Write-Host "Verified $($files.Count) payload files and game compatibility.";return}
if(Test-Path -LiteralPath $receiptPath){
    $old=Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    if($old.PackageHash -eq (Hash $manifestPath)){
        $ok=$true
        foreach($entry in @($old.Files)){
            if($entry.Kind -eq 'Settings'){continue}
            $target=SafePath $GamePath $entry.Path
            if(-not [IO.File]::Exists($target) -or (Hash $target) -ne $entry.InstalledHash){$ok=$false;break}
        }
        if($ok){Write-Host 'This exact package is already installed.';return}
    }
    throw 'A managed installation already exists. Uninstall it first (backups are preserved), then install this package.'
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
$isolatedFolder=$null
if($useSeparateLoader){
    $isolatedFolder='ue4ss-rka-'+[guid]::NewGuid().ToString('N').Substring(0,12)
    $separatePath=SafePath $GamePath ('platform/steam/'+$isolatedFolder)
    if(Test-Path -LiteralPath $separatePath){throw 'Separate UE4SS folder already exists. Run again to choose a new folder.'}
}
$plan=@(foreach($entry in $files){
    $relative=$entry.Path
    $kind=$entry.Kind
    if($useSeparateLoader){
        if($relative -eq $proxyPath){continue} # Change the startup files after the payload is in place.
        if($relative.StartsWith($ue4ssPrefix,[StringComparison]::OrdinalIgnoreCase)){
            $relative='platform/steam/'+$isolatedFolder+'/'+$relative.Substring($ue4ssPrefix.Length)
            $kind='Isolated'
        }
    }
    [pscustomobject]@{Path=$relative;Kind=$kind;Source=$sources[$entry.Path];SHA256=$entry.SHA256}
})
if($useSeparateLoader){
    $newOverride=SafePath $session 'override.txt'
    [IO.File]::WriteAllText($newOverride,$isolatedFolder,[Text.Encoding]::ASCII)
    $plan+=[pscustomobject]@{Path=$overridePath;Kind='Isolated';Source=$newOverride;SHA256=(Hash $newOverride)}
    $proxySource=$sources[$proxyPath]
    $plan+=[pscustomobject]@{Path=$proxyPath;Kind='Isolated';Source=$proxySource;SHA256=(Hash $proxySource)}
}
$records=@();$touched=@()
try {
    foreach($entry in $plan){
        $target=SafePath $GamePath $entry.Path
        # The existing loader and shared files are not owned by this mod.
        if($entry.Kind -eq 'Loader' -and (Test-Path -LiteralPath $target)){continue}
        if($entry.Kind -eq 'Settings' -and (Test-Path -LiteralPath $target)){continue}
        $backup=$null
        $backupHash=$null
        if(Test-Path -LiteralPath $target){
            $backup=$run+'/previous/'+$entry.Path
            $backupFile=SafePath $stateRoot $backup
            Put $target $backupFile
            $backupHash=Hash $backupFile
        }
        $record=[pscustomobject]@{Path=$entry.Path;InstalledHash=$entry.SHA256;Backup=$backup;BackupHash=$backupHash;Kind=$entry.Kind}
        Put $entry.Source $target
        $touched+=$record
        $records+=$record
    }
    $pendingReceipt=SafePath $session 'receipt.json'
    [pscustomobject]@{Version=$manifest.Version;PackageHash=(Hash $manifestPath);Files=@($records);SaveBackup=$run+'/saves'} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $pendingReceipt -Encoding UTF8
    [IO.File]::Move($pendingReceipt,$receiptPath)
}catch{
    $failure=$_
    [array]::Reverse($touched)
    $rollbackErrors=@()
    foreach($entry in $touched){
        try{
            $target=SafePath $GamePath $entry.Path
            if($entry.Backup){Put (SafePath $stateRoot $entry.Backup) $target}
            else{[IO.File]::Delete($target)}
        }catch{$rollbackErrors+="$($entry.Path): $($_.Exception.Message)"}
    }
    if($rollbackErrors.Count){Write-Warning ("Could not restore: "+($rollbackErrors -join '; ')+". Backups: $session")}
    throw $failure
}
Write-Host 'Installed. Load a save; Ringed Knight Sword is added to the weapon bag automatically. Equip it manually.' -ForegroundColor Green
Write-Host "Backup: $session"
