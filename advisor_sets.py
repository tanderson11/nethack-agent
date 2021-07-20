from advisors import *

small_advisors = [
    FreeImprovementAdvisorLevel({EnhanceSkillsAdvisor: 1,}),
    CriticallyInjuredAndUnthreatenedAdvisorLevel({FallbackSearchAdvisor: 1,}),
    CriticallyInjuredAdvisorLevel({
        DrinkHealingPotionAdvisor: 1,
        ZapTeleportOnSelfAdvisor: 1,
        ReadTeleportAdvisor: 1,
    }),
    CriticallyInjuredAdvisorLevel({PrayWhenCriticallyInjuredAdvisor: 1,}),
    MajorTroubleAdvisorLevel({PrayWhenMajorTroubleAdvisor: 1,}),
    WeakWithHungerAdvisorLevel({EatTopInventoryAdvisor: 1,}),
    WeakWithHungerAdvisorLevel({PrayWhenWeakAdvisor: 1,}),
    AdjacentToMonsterAndLowHpAdvisorLevel({RandomUnthreatenedMoveAdvisor: 1}),
    AdjacentToMonsterAdvisorLevel({RandomSafeMeleeAttack: 1,}),
    AdjacentToMonsterAdvisorLevel({RandomRangedAttackAdvisor: 1,}),
    AdjacentToMonsterAdvisorLevel({RandomUnthreatenedMoveAdvisor: 1,}), # we can't ranged attack, can we move to an unthreatened place?
    AdjacentToMonsterAdvisorLevel({MostNovelMoveAdvisor: 1,}), # okay can we just avoid it? 
    AdjacentToMonsterAdvisorLevel({
        RandomAttackAdvisor: 1, # even unsafe, only reach if we can't melee or ranged or move
        FallbackSearchAdvisor: 40, # basically controls to probability we yolo attack floating eyes
        }),
    AmUnthreatenedAdvisorLevel({
        PickupFoodAdvisor: 1,
        PickupArmorAdvisor: 1,
        EatCorpseAdvisor: 1,
        WearTopInventoryAdvisor: 1,
    }),
    DungeonsOfDoomAdvisorLevel({KickLockedDoorAdvisor: 1,}),
    AdvisorLevel({FreshCorpseMoveAdvisor: 1,}),
    AdvisorLevel({DesirableObjectMoveAdvisor: 1,}, skip_probability=0.3),
    AdvisorLevel({VisitUnvisitedSquareAdvisor: 1}),
    NoUnvisitedWalkableInFullVisionAdvisorLevel({TravelToUnexploredSquareAdvisor: 1}, skip_probability=0.8),
    AdvisorLevel({TakeDownstairsAdvisor: 1,}),
    AdvisorLevel({TravelToDownstairsAdvisor: 1,}, skip_probability=0.75),
    NoUnvisitedWalkableInFullVisionAdvisorLevel({SearchUndersearchedAdvisor: 1}, skip_probability=0.5),
    #AdvisorLevel({VisitUndersearchedSquareByNoveltyAdvisor: 1}, skip_probability=0.6),
    AdvisorLevel({
        MostNovelUnthreatenedMoveAdvisor: 10,
        RandomUnthreatenedMoveAdvisor: 2,
        DesirableObjectMoveAdvisor: 2,
        #FallbackSearchAdvisor: 1,
    }),
]