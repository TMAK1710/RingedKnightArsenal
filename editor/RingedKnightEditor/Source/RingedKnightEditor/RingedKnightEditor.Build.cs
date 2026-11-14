using UnrealBuildTool;
public class RingedKnightEditor : ModuleRules {
    public RingedKnightEditor(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage=PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[]{"Core","CoreUObject","Engine","GameplayTags"});
        PrivateDependencyModuleNames.AddRange(new string[]{"UnrealEd","AssetRegistry","Json","JsonUtilities"});
    }
}
