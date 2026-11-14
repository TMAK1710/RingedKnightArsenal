$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$env:TEMP=Join-Path $root 'build/tmp';$env:TMP=$env:TEMP;New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$build=Join-Path $root 'build\native';$sdk=Join-Path $root 'tools\native-deps\ue4ss-1ceefac8'
$dll=Join-Path $root 'tools\UE4SS\ue4ss\UE4SS.dll'
if((Get-FileHash -LiteralPath $dll).Hash -ne 'E1FB9A7E1D868AFEF6A091C2012E711C3EC47F05D100BA37F9631A4F75F31DF2'){throw 'Unexpected loader binary'}
New-Item -ItemType Directory -Force -Path (Join-Path $build 'include\Mod') | Out-Null
$header=[IO.File]::ReadAllText((Join-Path $sdk 'UE4SS\include\Mod\CppUserModBase.hpp'))
if(-not $header.Contains('#include <GUI/GUITab.hpp>')){throw 'SDK header changed'}
$header=$header.Replace('#include <GUI/GUITab.hpp>','namespace RC::GUI { class GUITab; }').Replace('GUI::GUITab::RenderFunctionType','void (*)(CppUserModBase*)')
[IO.File]::WriteAllText((Join-Path $build 'include\Mod\CppUserModBase.hpp'),$header,[Text.UTF8Encoding]::new($false))
$dev='C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat'
$environment=& $env:ComSpec /d /s /c "`"$dev`" -no_logo -arch=x64 -host_arch=x64 >nul && set"
if($LASTEXITCODE -ne 0){throw 'MSVC environment failed'}
foreach($line in $environment){if($line -match '^([^=]+)=(.*)$'){[Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process')}}
$exports=& dumpbin /nologo /exports $dll
$symbols=@($exports|ForEach-Object {if($_ -match '^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(\S+)'){$matches[1]}})
if($symbols.Count -lt 1000){throw 'Loader exports invalid'}
@('LIBRARY UE4SS.dll','EXPORTS')+$symbols | Set-Content -LiteralPath (Join-Path $build 'UE4SS.def') -Encoding ascii
& lib /nologo /machine:x64 ('/def:'+(Join-Path $build 'UE4SS.def')) ('/out:'+(Join-Path $build 'UE4SS.lib'))
if($LASTEXITCODE -ne 0){throw 'Import lib failed'}
$includes=@((Join-Path $build 'include'),(Join-Path $sdk 'UE4SS\include'),(Join-Path $root 'tools\native-deps\fmt-11.2.0\include'))
foreach($name in @('String','File','Input','LuaMadeSimple','LuaRaw')){$includes+=Join-Path $sdk ('deps\first\'+$name+'\include')}
Push-Location $root
try {
    & python (Join-Path $root 'src/test_native_schema_contract.py')
    if($LASTEXITCODE -ne 0){throw 'C++/runtime protection schema contract checks failed'}
    & python (Join-Path $root 'src/inspect_native_protection_contract.py')
    if($LASTEXITCODE -ne 0){throw 'C++/current-UHT protection schema checks failed'}
    & python (Join-Path $root 'src/inspect_art_resource_contract.py')
    if($LASTEXITCODE -ne 0){throw 'Art resource original/current-executable schema checks failed'}
    & python (Join-Path $root 'src/test_native_spatial_query.py')
    if($LASTEXITCODE -ne 0){throw 'Native spatial query ownership/batch contract checks failed'}
    if(-not(Test-Path -LiteralPath reports\ue-native-guard-map.txt)){throw 'Export the actual UE guard map before building the candidate'}
    & cl /nologo /std:c++latest /MD /O2 /EHsc /utf-8 ('/Fo'+(Join-Path $build 'test_guard_map.obj')) ('/Fe'+(Join-Path $build 'test_guard_map.exe')) 'src/native/test_guard_map.cpp'
    if($LASTEXITCODE -ne 0){throw 'Guard map check compilation failed'}
    & (Join-Path $build 'test_guard_map.exe') (Join-Path $root 'reports\ue-native-guard-map.txt')
    if($LASTEXITCODE -ne 0){throw 'Guard map checks failed'}
    & cl /nologo /std:c++latest /MD /O2 /EHsc /utf-8 ('/Fo'+(Join-Path $build 'test_guard_contact.obj')) ('/Fe'+(Join-Path $build 'test_guard_contact.exe')) 'src/native/test_guard_contact.cpp'
    if($LASTEXITCODE -ne 0){throw 'Guard contact check compilation failed'}
    & (Join-Path $build 'test_guard_contact.exe')
    if($LASTEXITCODE -ne 0){throw 'Guard contact checks failed'}
    & cl /nologo /std:c++latest /MD /O2 /EHsc /utf-8 ('/Fo'+(Join-Path $build 'test_hit_packet.obj')) ('/Fe'+(Join-Path $build 'test_hit_packet.exe')) 'src/native/test_hit_packet.cpp'
    if($LASTEXITCODE -ne 0){throw 'Hit packet check compilation failed'}
    & (Join-Path $build 'test_hit_packet.exe') (Join-Path $root 'src/runtime/RingedKnightArsenal/Scripts/combat-profile.json') (Join-Path $root 'src/native/NativeHit.hpp')
    if($LASTEXITCODE -ne 0){throw 'Hit packet checks failed'}
    & cl /nologo /std:c++latest /MD /O2 /EHsc /utf-8 ('/Fo'+(Join-Path $build 'test_protection_lifecycle.obj')) ('/Fe'+(Join-Path $build 'test_protection_lifecycle.exe')) 'src/native/test_protection_lifecycle.cpp'
    if($LASTEXITCODE -ne 0){throw 'Protection lifecycle check compilation failed'}
    & (Join-Path $build 'test_protection_lifecycle.exe') (Join-Path $root 'src/native/main.cpp') (Join-Path $root 'src/native/NativeProtection.hpp')
    if($LASTEXITCODE -ne 0){throw 'Protection lifecycle checks failed'}
    & cl /nologo /std:c++latest /MD /O2 /EHsc /utf-8 ('/Fo'+(Join-Path $build 'test_signature_names.obj')) ('/Fe'+(Join-Path $build 'test_signature_names.exe')) 'src/native/test_signature_names.cpp'
    if($LASTEXITCODE -ne 0){throw 'Native FName parameter check compilation failed'}
    & (Join-Path $build 'test_signature_names.exe')
    if($LASTEXITCODE -ne 0){throw 'Native FName parameter checks failed'}
    & cl /nologo /std:c++latest /MD /O2 /EHsc /utf-8 ('/Fo'+(Join-Path $build 'test_protection_strings.obj')) ('/Fe'+(Join-Path $build 'test_protection_strings.exe')) 'src/native/test_protection_strings.cpp'
    if($LASTEXITCODE -ne 0){throw 'Protection FString check compilation failed'}
    & (Join-Path $build 'test_protection_strings.exe') (Join-Path $root 'src/native/NativeProtection.hpp')
    if($LASTEXITCODE -ne 0){throw 'Protection FString checks failed'}
    & cl /nologo /std:c++latest /MD /O2 /EHsc /utf-8 ('/Fo'+(Join-Path $build 'test_process_validation_cache.obj')) ('/Fe'+(Join-Path $build 'test_process_validation_cache.exe')) 'src/native/test_process_validation_cache.cpp'
    if($LASTEXITCODE -ne 0){throw 'Process validation cache check compilation failed'}
    & (Join-Path $build 'test_process_validation_cache.exe') (Join-Path $root 'src/native/main.cpp') (Join-Path $root 'src/native/ShieldGate.hpp')
    if($LASTEXITCODE -ne 0){throw 'Process validation cache checks failed'}
    & cl /nologo /std:c++latest /MD /O2 /EHsc /utf-8 ('/Fo'+(Join-Path $build 'test_inventory_row_name.obj')) ('/Fe'+(Join-Path $build 'test_inventory_row_name.exe')) 'src/native/test_inventory_row_name.cpp'
    if($LASTEXITCODE -ne 0){throw 'Inventory row-name check compilation failed'}
    & (Join-Path $build 'test_inventory_row_name.exe')
    if($LASTEXITCODE -ne 0){throw 'Inventory row-name checks failed'}
    & cl /nologo /std:c++latest /MD /O2 /EHsc /utf-8 ('/Fo'+(Join-Path $build 'test_art_resource.obj')) ('/Fe'+(Join-Path $build 'test_art_resource.exe')) 'src/native/test_art_resource.cpp'
    if($LASTEXITCODE -ne 0){throw 'Art resource policy compilation failed'}
    & (Join-Path $build 'test_art_resource.exe')
    if($LASTEXITCODE -ne 0){throw 'Art resource policy checks failed'}
    $opts=@('/nologo','/c','/std:c++latest','/MD','/O2','/EHsc','/W3','/permissive-','/Zc:__cplusplus','/utf-8','/Brepro','/DNDEBUG','/D_ITERATOR_DEBUG_LEVEL=0','/DNOMINMAX','/DWIN32_LEAN_AND_MEAN')
    $opts+=@($includes|ForEach-Object {'/I'+$_})
    & cl @opts ('/Fo'+(Join-Path $build 'main.obj')) 'src\native\main.cpp'
    if($LASTEXITCODE -ne 0){throw 'Native compilation failed'}
    $objects=@((Join-Path $build 'main.obj'))
    foreach($file in @('buffer','hook','trampoline','hde/hde64')){
        $obj=Join-Path $build ($file.Replace('/','-')+'.obj')
        & cl /nologo /c /TC /MD /O2 /DNDEBUG ('/Fo'+$obj) ('references/pbz-mc/third_party/minhook-1.3.4/src/'+$file+'.c')
        if($LASTEXITCODE -ne 0){throw 'MinHook compilation failed'}
        $objects+=$obj
    }
    & link /NOLOGO /DLL /MACHINE:X64 /OPT:REF /OPT:ICF /DYNAMICBASE /NXCOMPAT /Brepro ('/OUT:'+(Join-Path $build 'main.dll')) @objects (Join-Path $build 'UE4SS.lib') bcrypt.lib user32.lib
    if($LASTEXITCODE -ne 0){throw 'Native link failed'}
    & dumpbin /nologo /imports (Join-Path $build 'main.dll') | Set-Content -LiteralPath (Join-Path $build 'imports.txt')
    Get-FileHash -LiteralPath (Join-Path $build 'main.dll')
} finally {Pop-Location}
