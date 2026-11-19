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
LOADER='platform/steam/ue4ss/UE4SS.dll'
PROXY='platform/steam/dwmapi.dll'
SETTINGS='platform/steam/ue4ss/UE4SS-settings.ini'
write(GAME/MOD,'previous-mod')
write(GAME/SETTINGS,'existing-settings')
entries=[]
for rel,kind,value in [(MOD,'Mod','release-mod'),(PROXY,'Loader','fake-proxy'),(LOADER,'Loader','fake-loader'),(SETTINGS,'Settings','default-settings')]:
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
    assert result.returncode==0 and 'Verified 4 payload files' in result.stdout,(result.stdout,result.stderr)
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
write(GAME/MOD,'release-mod');run('Uninstall')
write(GAME/LOADER,'incompatible-loader');assert 'UE4SS core differs' in run('Install',False)
assert (GAME/MOD).read_text()=='previous-mod';write(GAME/LOADER,'fake-loader')
write(GAME/PROXY,'existing-proxy')
assert 'core matches' in run('Verify')
assert 'Canceled' in run('Install',response='n\n')
assert (GAME/MOD).read_text()=='previous-mod'
run('Install',response='y\n')
assert (GAME/PROXY).read_text()=='existing-proxy' and (GAME/MOD).read_text()=='release-mod'
assert 'already installed' in run('Install')
run('Uninstall')
assert (GAME/PROXY).read_text()=='existing-proxy' and (GAME/MOD).read_text()=='previous-mod'
override=GAME/'platform/steam/override.txt'
write(override,'somewhere else');assert 'different UE4SS location' in run('Install',False);override.unlink()
(GAME/LOADER).unlink();assert 'UE4SS.dll is missing' in run('Install',False);write(GAME/LOADER,'fake-loader')
assert (GAME/PROXY).read_text()=='existing-proxy' and (GAME/MOD).read_text()=='previous-mod'
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
print(json.dumps({'result':'PASS','checks':['steam-discovery-missing-drive','folder-picker-fallback','install','backup','uninstall-restore','shared-loader-retained','other-mod-preserved','settings-preserved','user-edit-preserved','loader-core-conflict','existing-proxy-opt-in','missing-core','custom-loader-path','corruption','game-version','path-escape','late-failure-rollback'],'fixture':str(CASE)}))
