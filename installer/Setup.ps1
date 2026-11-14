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
        if(Test-Path $key){$v=Get-ItemProperty $key;foreach($n in @('SteamPath','InstallPath')){if($v.PSObject.Properties.Name -contains $n){$roots+=([string]$v.$n)}}}
    }
    $libraries=@($roots)
    foreach($root in $roots){$vdf=Join-Path $root 'steamapps/libraryfolders.vdf';if(Test-Path -LiteralPath $vdf){
        foreach($m in [regex]::Matches([IO.File]::ReadAllText($vdf),'"path"\s+"([^"]+)"')){$libraries+=$m.Groups[1].Value.Replace('\\','\')}
    }}
    $found=@($libraries | ForEach-Object {Join-Path $_ 'steamapps/common/PBZ'} | Select-Object -Unique | Where-Object {Test-Path -LiteralPath (Join-Path $_ 'platform/steam/PBZ.exe')})
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
$seen=@{}
foreach($entry in $files){
    if($seen.ContainsKey($entry.Path)){throw 'Duplicate package destination'};$seen[$entry.Path]=$true
    $source=SafePath (Join-Path $PackageRoot 'payload') $entry.Path
    $target=SafePath $GamePath $entry.Path
    if((Hash $source) -ne $entry.SHA256){throw "Damaged package: $($entry.Path)"}
    if($entry.Kind -eq 'Loader' -and (Test-Path -LiteralPath $target) -and (Hash $target) -ne $entry.SHA256){throw "Different UE4SS installation detected: $($entry.Path). Kept untouched; resolve loader compatibility first."}
}
if($Action -eq 'Verify'){Write-Host "Verified $($files.Count) payload files and game compatibility.";return}
if(Test-Path -LiteralPath $receiptPath){
    $old=Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    if($old.PackageHash -eq (Hash (Join-Path $PackageRoot 'manifest.json'))){
        $ok=$true;foreach($entry in $files){if($entry.Kind -eq 'Settings'){continue};$t=SafePath $GamePath $entry.Path;if(-not(Test-Path -LiteralPath $t) -or (Hash $t) -ne $entry.SHA256){$ok=$false;break}}
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
$records=@();$touched=@()
try {
    foreach($entry in $files){
        $target=SafePath $GamePath $entry.Path
        # Identical existing loader/shared files are not owned by this mod.
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
