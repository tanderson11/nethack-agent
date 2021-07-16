from advisors import *

small_advisors = [
    FreeImprovementAdvisorLevel({EnhanceSkillsAdvisor: 1,}),
    CriticallyInjuredAndUnthreatenedAdvisorLevel({ # let's try to pray less in the early game by not praying if unthreatened
        LeastNovelNonObjectGlyphMoveAdvisor: 5, # try not to step on traps by only moving to areas that are floor glyphs
        FallbackSearchAdvisor: 5,
    }),
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
        FallbackSearchAdvisor: 40,
        }),
    AmUnthreatenedAdvisorLevel({
        PickupAdvisor: 1,
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


large_advisors = [
    FreeImprovementAdvisorLevel({EnhanceSkillsAdvisor: 1,}),
    CriticallyInjuredAndUnthreatenedAdvisorLevel({ # let's try to pray less in the early game by not praying if unthreatened
            LeastNovelNonObjectGlyphMoveAdvisor: 3, # try not to step on traps by only moving to areas that are floor glyphs
            FallbackSearchAdvisor: 7,
            DrinkHealingPotionAdvisor: 1
        }),
    CriticallyInjuredAdvisorLevel({
            DrinkHealingPotionAdvisor: 15,
            ZapTeleportOnSelfAdvisor: 1,
            ReadTeleportAdvisor: 10,
        }),
    CriticallyInjuredAdvisorLevel({PrayerAdvisor: 1,}),
    MajorTroubleAdvisorLevel({PrayerAdvisor: 1,}),
    ThreatenedMoreThanOnceAdvisorLevel({LeastNovelUnthreatenedMoveAdvisor: 1,}),
    WeakWithHungerAdvisorLevel({EatTopInventoryAdvisor: 1,}),
    WeakWithHungerAdvisorLevel({PrayerAdvisor: 1,}),
    AdjacentToMonsterAndLowHpAdvisorLevel({LeastNovelUnthreatenedMoveAdvisor: 1}),
    AdjacentToMonsterAdvisorLevel({
        RandomSafeMeleeAttack: 1,
        }),
    AdjacentToMonsterAdvisorLevel({ # should only reach if we have no safe melee
        RandomRangedAttackAdvisor: 1,
        MostNovelUnthreatenedMoveAdvisor: 3,
        }),
    LowHPAdvisorLevel({ # safe actions to do when we're at low hp
        PickupAdvisor: 5,
        FallbackSearchAdvisor: 30,
        RandomUnthreatenedMoveAdvisor: 1,
        }),
    AmUnthreatenedAdvisorLevel({
        PickupAdvisor: 1,
        EatCorpseAdvisor: 1,
    }),
    DungeonsOfDoomAdvisorLevel({KickLockedDoorAdvisor: 1,}), # don't kick doors in other branches bc minetown
    AdvisorLevel({TakeDownstairsAdvisor: 1,}),
    AllMovesThreatenedAdvisorLevel({
            FallbackSearchAdvisor: 50,
            RandomMoveAdvisor: 15,
            RandomAttackAdvisor: 1, # even nasty
        }),
    AdvisorLevel({
        FreshCorpseMoveAdvisor: 1500,
        DesirableObjectMoveAdvisor: 500,
        MostNovelUnthreatenedMoveAdvisor: 100,
        NoUnexploredSearchAdvisor: 100,
        RandomUnthreatenedMoveAdvisor: 5,
        MostNovelMoveAdvisor: 1,
        TravelToDownstairsAdvisor: 5,
        }),
    AdvisorLevel({FallbackSearchAdvisor: 1,}),
]