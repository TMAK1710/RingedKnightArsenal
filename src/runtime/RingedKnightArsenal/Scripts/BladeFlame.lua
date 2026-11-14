-- Sword component coordinates in centimeters. The native Minimal renderer's
-- compiled local mesh extends +8.060 to +450.057 along Z. After this
-- transform its core covers the measured steel edge from -30.457 to -111.485.
-- Apply the placement and emitter overrides before activating the system.
return {
    location = {X = 0.056, Y = 0.484, Z = -28.979447},
    rotation = {Pitch = 0, Yaw = 0, Roll = 180},
    scale = 0.183322518,
    disabled_emitters = {
        'NE_Template_BladeTrail',
        'NE_Slash_HighLight',
        'NE_Template_BladeTrail003',
        'NE_Template_BladeTrail007',
        'Minimal004',
        'Minimal005',
    },
}
