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
    #AdjacentToManyMonstersAdvisorLevel({RandomUnthreatenedMoveAdvisor: 1}),
    AdjacentToDangerousMonsterAndLowHpAdvisorLevel({RandomUnthreatenedMoveAdvisor: 1}),
    AdjacentToMonsterAdvisorLevel({SafeMeleeAttackAdvisor: 1,}),
    AdjacentToMonsterAdvisorLevel({RandomRangedAttackAdvisor: 1,}),
    AdjacentToMonsterAdvisorLevel({RandomUnthreatenedMoveAdvisor: 1,}), # we can't ranged attack, can we move to an unthreatened place?
    AdjacentToMonsterAdvisorLevel({MostNovelMoveAdvisor: 1,}), # okay can we just avoid it? 
    AdjacentToMonsterAdvisorLevel({
        RandomNonPeacefulMeleeAttackAdvisor: 1, # even unsafe, only reach if we can't melee or ranged or move
        FallbackSearchAdvisor: 10, # basically controls to probability we yolo attack floating eyes
        }),
    #SafeAdvisorLevel({IdentifyPotentiallyMagicArmorAdvisor: 1}),
    SafeAdvisorLevel({WearEvenBlockedArmorAdvisor: 1}),
    AmUnthreatenedAdvisorLevel({
        PickupFoodAdvisor: 1,
        PickupArmorAdvisor: 1,
        EatCorpseAdvisor: 1,
        WearUnblockedArmorAdvisor: 1,
        EngraveTestWandsAdvisor: 1,
    }),
    AdvisorLevel({HuntNearestWeakEnemyAdvisor: 1}),
    #AdvisorLevel({TravelToUnexploredSquareAdvisor: 1,}, skip_probability=0.96),
    UnthreatenedLowHPAdvisorLevel({FallbackSearchAdvisor: 1,}),
    AdvisorLevel({OpenClosedDoorAdvisor: 1,}),
    DungeonsOfDoomAdvisorLevel({KickLockedDoorAdvisor: 1,}),
    AdvisorLevel({TraverseUnknownUpstairsAdvisor: 1,}),
    GnomishMinesAdvisorLevel({UpstairsAdvisor: 1,}),
    AdvisorLevel({TakeDownstairsAdvisor: 1,}),
    AdvisorLevel({FreshCorpseMoveAdvisor: 1,}),
    AdvisorLevel({VisitUnvisitedSquareAdvisor: 1}),
    AdvisorLevel({
        MostNovelUnthreatenedMoveAdvisor: 10,
        NoUnexploredSearchAdvisor: 6,
        RandomUnthreatenedMoveAdvisor: 2,
        DesirableObjectMoveAdvisor: 2,
        TravelToDownstairsAdvisor: 1,
    }),
]