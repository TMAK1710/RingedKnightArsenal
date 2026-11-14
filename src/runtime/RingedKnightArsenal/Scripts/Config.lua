return {
    version='0.9.16-local',auto_grant=true,development_bridge=false,
    -- Temporary user-requested testing override; native paid policy is retained.
    testing_free_art=true,
    -- Verified against PBZ IMC_Default and IMC_Deflect; L2 is this mod's art.
    keys={attack={'LeftMouseButton','Gamepad_FaceButton_Left'},guard={'RightMouseButton','Gamepad_LeftShoulder'},
        art={'Q','Gamepad_LeftTrigger'},triangle={'F','Gamepad_FaceButton_Top'}},
    art_chord={guard='Gamepad_LeftShoulder',attack='Gamepad_FaceButton_Right'},
    vfx={flame='/PBZVFXPack/VFX/BattleFX/Weapon/HeiShang/NS_LongBlade_Fire_101.NS_LongBlade_Fire_101',
        explosion='/Game/PBZContent/VFX/SceneFX/Common/NS_BarrelExplosion_303.NS_BarrelExplosion_303'},
    assets={sword='/HuaShira/Mods/RingedKnight/Meshes/SM_RingedKnightStraightSword.SM_RingedKnightStraightSword',
        shield='/HuaShira/Mods/RingedKnight/Meshes/SM_BlackKnightShield.SM_BlackKnightShield',
        bomb='/HuaShira/Mods/RingedKnight/Meshes/SM_RopeBlackFirebomb.SM_RopeBlackFirebomb'},
    runtime_verified=false
}
