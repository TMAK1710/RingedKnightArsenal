"""Exercise the real portable setup in disposable F-drive fixtures."""
import hashlib,json,subprocess,shutil,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/release-tests';BASE.mkdir(parents=True,exist_ok=True)
CASE=Path(tempfile.mkdtemp(prefix='setup-',dir=BASE))
GAME=CASE/'game';PACKAGE=CASE/'package';PACKAGE.mkdir()
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
write(GAME/'platform/steam/PBZ.exe','fake executable; never started')
SAVE=GAME/'ProjectPBZ/Saved/SaveGames/test.sav';write(SAVE,'original-save')
OTHER=GAME/'platform/steam/ue4ss/Mods/OtherMod/Scripts/main.lua';write(OTHER,'unrelated-mod')
MOD='platform/steam/ue4ss/Mods/RingedKnightArsenal/Scripts/main.lua'
MOD_MARKER='platform/steam/ue4ss/Mods/RingedKnightArsenal/enabled.txt'
LOADER='platform/steam/ue4ss/UE4SS.dll'
PROXY='platform/steam/dwmapi.dll'
SETTINGS='platform/steam/ue4ss/UE4SS-settings.ini'
write(GAME/MOD,'previous-mod')
write(GAME/SETTINGS,'existing-settings')
entries=[]
for rel,kind,value in [(MOD,'Mod','release-mod'),(MOD_MARKER,'Mod',''),(PROXY,'Loader','fake-proxy'),(LOADER,'Loader','fake-loader'),(SETTINGS,'Settings','default-settings')]:
    p=PACKAGE/'payload'/rel;write(p,value);entries.append(dict(Path=rel,Kind=kind,SHA256=sha(p)))
manifest=dict(Version='fixture',GameSHA256=sha(GAME/'platform/steam/PBZ.exe'),Files=entries)
def save_manifest():write(PACKAGE/'manifest.json',json.dumps(manifest))
save_manifest()
def verify_discovery(library_has_game):
    steam=CASE/'Steam'
    libraries=steam/'steamapps/libraryfolders.vdf'
    library_path=str(CASE).replace('\\','\\\\')
    write(libraries, f'"libraryfolders" {{ "0" {{ "path" "__MISSING_DRIVE__" }} "1" {{ "path" "{library_path}" }} }}')
    if library_has_game:
        p=CASE/'steamapps/common/PBZ/platform/steam/PBZ.exe'
        write(p,(GAME/'platform/steam/PBZ.exe').read_text())
    else:
        (CASE/'steamapps/common/PBZ/platform/steam/PBZ.exe').unlink()
    wrapper=CASE/'verify-discovery.ps1'
    write(wrapper,r"""
param($Setup,$SteamRoot,$PackageRoot,$ManualGamePath,[int]$ExpectAutomatic)
$ErrorActionPreference='Stop'
$usedLetters=[IO.DriveInfo]::GetDrives() | ForEach-Object {$_.Name.Substring(0,1)}
$missingLetter='Z','Y','X','W','V','U' | Where-Object {$_ -notin $usedLetters -and -not (Get-PSDrive -Name $_ -ErrorAction SilentlyContinue)} | Select-Object -First 1
if(-not $missingLetter){throw 'No unused drive letter for test'}
$missingRoot="${missingLetter}:\SteamLibrary"
$vdf=[IO.Path]::Combine($SteamRoot,'steamapps/libraryfolders.vdf')
[IO.File]::WriteAllText($vdf,[IO.File]::ReadAllText($vdf).Replace('__MISSING_DRIVE__',$missingRoot.Replace('\','\\')))
function Get-ItemProperty {
    param([Alias('LiteralPath')]$Path)
    if($Path -like 'HKCU:*'){[pscustomobject]@{SteamPath=$SteamRoot}}
    else{[pscustomobject]@{InstallPath=$missingRoot}}
}
function Add-Type {
    param($AssemblyName)
    if($ExpectAutomatic){throw 'Opened a folder picker despite finding the game'}
}
function New-Object {
    param($TypeName)
    if($TypeName -ne 'Windows.Forms.FolderBrowserDialog'){throw "Unexpected type $TypeName"}
    $dialog=[pscustomobject]@{Description='';SelectedPath=$ManualGamePath}
    $dialog | Add-Member -MemberType ScriptMethod -Name ShowDialog -Value {Write-Host 'Folder picker reached';'OK'}
    $dialog
}
& $Setup -Action Verify -PackageRoot $PackageRoot
""")
    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(wrapper),
        str(ROOT/'installer/Setup.ps1'),str(steam),str(PACKAGE),str(GAME),str(int(library_has_game))],
        capture_output=True,text=True)
    assert result.returncode==0 and 'Verified 5 payload files' in result.stdout,(result.stdout,result.stderr)
    assert ('Folder picker reached' in result.stdout) != library_has_game,result.stdout

verify_discovery(library_has_game=True)
verify_discovery(library_has_game=False)
def run(action,ok=True,response=None):
    p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'installer/Setup.ps1'),'-Action',action,'-GamePath',str(GAME),'-PackageRoot',str(PACKAGE)],capture_output=True,text=True,input=response)
    assert (p.returncode==0)==ok,(action,p.stdout,p.stderr)
    return p.stdout+p.stderr
run('Verify');run('Install')
assert 'already installed' in run('Install')
assert (GAME/MOD).read_text()=='release-mod'
assert (GAME/SETTINGS).read_text()=='existing-settings'
assert OTHER.read_text()=='unrelated-mod' and SAVE.read_text()=='original-save'
assert list((GAME/'RingedKnightArsenal-Backup').glob('install-*/saves/test.sav'))
# Existing custom settings are preserved; same-install check should ignore them.
run('Uninstall');assert (GAME/MOD).read_text()=='previous-mod'
assert (GAME/LOADER).read_text()=='fake-loader'
assert OTHER.read_text()=='unrelated-mod' and SAVE.read_text()=='original-save'
run('Install');write(GAME/MOD,'user-edit');run('Uninstall',False)
assert (GAME/MOD).read_text()=='user-edit'
assert (GAME/MOD_MARKER).is_file()
write(GAME/MOD,'release-mod');run('Uninstall')
override=GAME/'platform/steam/override.txt'
for original_core,original_override in [('fake-loader',None),(None,None),('old-core','old-loader-directory')]:
    write(GAME/PROXY,'existing-proxy')
    if original_core is None:
        (GAME/LOADER).unlink()
    else:
        write(GAME/LOADER,original_core)
    if original_override is not None:
        write(override,original_override)
    assert 'separate UE4SS folder' in run('Verify')
    assert 'separate UE4SS folder' in run('Install')
    separate=override.parent/override.read_text()
    assert separate.name.startswith('ue4ss-rka-')
    assert (separate/'UE4SS.dll').read_text()=='fake-loader'
    assert (separate/Path(MOD).relative_to('platform/steam/ue4ss')).read_text()=='release-mod'
    assert (GAME/PROXY).read_text()=='fake-proxy'
    assert (GAME/MOD).read_text()=='previous-mod' and OTHER.read_text()=='unrelated-mod'
    assert 'already installed' in run('Install')
    run('Uninstall')
    assert not (separate/'UE4SS.dll').exists()
    assert (GAME/PROXY).read_text()=='existing-proxy'
    if original_core is None:
        assert not (GAME/LOADER).exists()
    else:
        assert (GAME/LOADER).read_text()==original_core
    if original_override is None:
        assert not override.exists()
    else:
        assert override.read_text()==original_override
        override.unlink()
    write(GAME/LOADER,'fake-loader')
write(GAME/PROXY,'fake-proxy')
write(GAME/SETTINGS,'[Overrides]\nModsFolderPath = E:/CustomMods')
assert 'custom UE4SS mod folders' in run('Install')
run('Uninstall')
assert (GAME/SETTINGS).read_text()=='[Overrides]\nModsFolderPath = E:/CustomMods'
write(GAME/SETTINGS,'existing-settings')
run('Install')
write(GAME/MOD,'previous-mod') # Simulate an interrupted uninstall after backup restore.
run('Uninstall')
assert not (GAME/MOD_MARKER).exists()
write(GAME/PROXY,'locked-existing-proxy')
write(override,'old-loader-directory')
lock_test=CASE/'setup-with-locked-proxy.ps1'
write(lock_test,r"""
param($Setup,$Game,$Package)
$ErrorActionPreference='Stop'
$proxy=[IO.Path]::Combine($Game,'platform/steam/dwmapi.dll')
$lock=[IO.File]::Open($proxy,'Open','Read','Read')
try{& $Setup -Action Install -GamePath $Game -PackageRoot $Package}finally{$lock.Dispose()}
""")
failed=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(lock_test),
    str(ROOT/'installer/Setup.ps1'),str(GAME),str(PACKAGE)],capture_output=True,text=True)
assert failed.returncode!=0 and 'Replace' in failed.stderr and 'Could not restore' not in failed.stdout,(failed.stdout,failed.stderr)
assert (GAME/PROXY).read_text()=='locked-existing-proxy' and override.read_text()=='old-loader-directory'
assert not list(override.parent.glob('ue4ss-rka-*/UE4SS.dll'))
assert not (GAME/'RingedKnightArsenal-Backup/installed.json').exists()
override.unlink()
write(GAME/PROXY,'fake-proxy')
write(PACKAGE/'payload'/MOD,'corrupt');run('Install',False);write(PACKAGE/'payload'/MOD,'release-mod')
manifest['GameSHA256']='0'*64;save_manifest();run('Install',False)
manifest['GameSHA256']=sha(GAME/'platform/steam/PBZ.exe');save_manifest()
manifest['Files'].append(dict(Path='../escape',Kind='Mod',SHA256='0'*64));save_manifest();run('Install',False)
manifest['Files'].pop();save_manifest()
# Force a late copy failure after the first mod has been replaced, then verify rollback.
rel='blocked/file.txt';write(PACKAGE/'payload'/rel,'new-file');write(GAME/'blocked','parent-is-file')
manifest['Files'].append(dict(Path=rel,Kind='Mod',SHA256=sha(PACKAGE/'payload'/rel)));save_manifest()
run('Install',False);assert (GAME/MOD).read_text()=='previous-mod'
assert SAVE.read_text()=='original-save' and OTHER.read_text()=='unrelated-mod'
print(json.dumps({'result':'PASS','checks':['steam-discovery-missing-drive','folder-picker-fallback','install','backup','uninstall-restore','uninstall-retry','uninstall-preflight','shared-loader-retained','other-mod-preserved','settings-preserved','isolated-loader-conflicts','original-proxy-and-override-restored','locked-proxy-rollback','custom-mods-folder','corruption','game-version','path-escape','late-failure-rollback'],'fixture':str(CASE)}))
