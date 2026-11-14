#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GameplayTagContainer.h"
#include "RingedKnightEditorLibrary.generated.h"
class USkeleton;
class UAnimSequence;
class UMaterialInstanceConstant;
class UMaterialInterface;
class UTexture;
UCLASS()
class RINGEDKNIGHTEDITOR_API URingedKnightEditorLibrary : public UBlueprintFunctionLibrary {
    GENERATED_BODY()
public:
    /** Build an editor-only placeholder with exact game bone names, order and rest transforms. Never package it. */
    UFUNCTION(BlueprintCallable,Category="RingedKnightBuild")
    static USkeleton* CreateReferenceSkeleton(const FString& PackagePath,const FString& JsonFile);
    /** Import sampled native-local bone tracks into a mod-owned animation. */
    UFUNCTION(BlueprintCallable,Category="RingedKnightBuild")
    static UAnimSequence* CreateAnimation(const FString& PackagePath,USkeleton* Skeleton,const FString& JsonFile);
    /** Exercise UE's actual property exporter for the native guard adapter. */
    UFUNCTION(BlueprintCallable,Category="RingedKnightBuild")
    static FString ExportGuardMap(const TMap<FGameplayTag,float>& AttackData);
    /** Store native equipment layer-zero overrides without compiling a new game shader permutation. */
    UFUNCTION(BlueprintCallable,Category="RingedKnightBuild")
    static bool ConfigureEquipmentMaterial(UMaterialInstanceConstant* Instance,UMaterialInterface* Parent,UTexture* Albedo,UTexture* Normal,UTexture* Mix,FLinearColor Tint,float Metallic,float Roughness);
    /** Sample the imported UE asset itself for comparison against exported local transforms. */
    UFUNCTION(BlueprintCallable,Category="RingedKnightBuild")
    static bool ExportAnimationSamples(UAnimSequence* Animation,const FString& JsonFile,bool bFullTimeline=false);
    UFUNCTION(BlueprintCallable,Category="RingedKnightBuild")
    static bool SetLosslessAnimationCompression(UAnimSequence* Animation,const FString& SettingsPath);
    UFUNCTION(BlueprintCallable,Category="RingedKnightBuild")
    static bool FinalizeAnimationCompression(UAnimSequence* Animation);
};
