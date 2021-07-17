from advisors import *

small_advisors = [
    FreeImprovementAdvisorLevel({EnhanceSkillsAdvisor: 1,}),
    CriticallyInjuredAndUnthreatenedAdvisorLevel({FallbackSearchAdvisor: 1,}),
    CriticallyInjuredAdvisorLevel({
        DrinkHealingPotionAdvisor: 1,
        ZapTeleportOnSelfAdvisor: 1,
        ReadTeleportAdvisor: 1,
    }),
    CriticallyInjuredAdvisorLevel({PrayerAdvisor: 1,}),
    MajorTroubleAdvisorLevel({PrayerAdvisor: 1,}),
    WeakWithHungerAdvisorLevel({EatTopInventoryAdvisor: 1,}),
    WeakWithHungerAdvisorLevel({PrayerAdvisor: 1,}),
    AdjacentToMonsterAndLowHpAdvisorLevel({RandomUnthreatenedMoveAdvisor: 1}),
    AdjacentToMonsterAdvisorLevel({RandomSafeMeleeAttack: 1,}),
    AdjacentToMonsterAdvisorLevel({RandomRangedAttackAdvisor: 1,}),
    AdjacentToMonsterAdvisorLevel({MostNovelMoveAdvisor: 1,}), # we can't ranged attack, can we at least try to move past?
    AdjacentToMonsterAdvisorLevel({
        RandomAttackAdvisor: 1, # even unsafe, only reach if we can't melee or ranged or move
        FallbackSearchAdvisor: 40, # basically controls to probability we yolo attack floating eyes
        }),
    AmUnthreatenedAdvisorLevel({
        PickupFoodAdvisor: 1,
        PickupArmorAdvisor: 1,
        EatCorpseAdvisor: 1,
    }),
    DungeonsOfDoomAdvisorLevel({KickLockedDoorAdvisor: 1,}),
    AdvisorLevel({TakeDownstairsAdvisor: 1,}),
    AdvisorLevel({FreshCorpseMoveAdvisor: 1,}),
    AdvisorLevel({
        MostNovelUnthreatenedMoveAdvisor: 10,
        NoUnexploredSearchAdvisor: 6,
        RandomUnthreatenedMoveAdvisor: 2,
        DesirableObjectMoveAdvisor: 2,
        TravelToDownstairsAdvisor: 1,
    }),
    AdvisorLevel({FallbackSearchAdvisor: 1,}),
]