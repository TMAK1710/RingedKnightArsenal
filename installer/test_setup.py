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
SETTINGS='platform/steam/ue4ss/UE4SS-settings.ini'
write(GAME/MOD,'previous-mod')
write(GAME/SETTINGS,'existing-settings')
entries=[]
for rel,kind,value in [(MOD,'Mod','release-mod'),(LOADER,'Loader','fake-loader'),(SETTINGS,'Settings','default-settings')]:
    p=PACKAGE/'payload'/rel;write(p,value);entries.append(dict(Path=rel,Kind=kind,SHA256=sha(p)))
manifest=dict(Version='fixture',GameSHA256=sha(GAME/'platform/steam/PBZ.exe'),Files=entries)
def save_manifest():write(PACKAGE/'manifest.json',json.dumps(manifest))
save_manifest()
def run(action,ok=True):
    p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'installer/Setup.ps1'),'-Action',action,'-GamePath',str(GAME),'-PackageRoot',str(PACKAGE)],capture_output=True,text=True)
    assert (p.returncode==0)==ok,(action,p.stdout,p.stderr)
    return p.stdout
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
write(GAME/LOADER,'incompatible-loader');run('Install',False)
assert (GAME/MOD).read_text()=='previous-mod';write(GAME/LOADER,'fake-loader')
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
print(json.dumps({'result':'PASS','checks':['install','backup','uninstall-restore','shared-loader-retained','other-mod-preserved','settings-preserved','user-edit-preserved','loader-conflict','corruption','game-version','path-escape','late-failure-rollback'],'fixture':str(CASE)}))
