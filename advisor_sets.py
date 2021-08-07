from advisors import *

new_advisors = [
    # FREE IMPROVEMENT
    SequentialCompositeAdvisor(advisors=[EnhanceSkillsAdvisor(),]),
    # STONING ILL ETC
    SequentialCompositeAdvisor(flags=flags.UrgentMajorTrouble, advisors=[PrayForUrgentMajorTroubleAdvisor()]),
    # CRITICALLY INJURED
    SequentialCompositeAdvisor(flags=flags.CriticallyInjured or flags.LifeThreatened, advisors=[ # dumb, doesn't work
        WaitAdvisor(threat_tolerance=0.),
        GoUpstairsAdvisor(carried_threat_tolerance=0.),
        DoCombatHealingAdvisor(),
        UseEscapeItemAdvisor(),
        PrayForHPAdvisor(),
        #EngraveElberethAdvisor(),
        #PathfindToSafetyAdvisor(path_threat_tolerance=0.3),
        ]),
    # WEAK
    SequentialCompositeAdvisor(flags=flags.WeakWithHunger, advisors=[CombatEatAdvisor(threat_tolerance=0.05)]),
    # HIGHLY THREATENED
    #SequentialCompositeAdvisor(threat_threshold=0.4, advisors=[PathfindToSafetyAdvisor()]),
    # IN GNOMISH MINES
    SequentialCompositeAdvisor(flags=flags.InGnomishMines, advisors=[GoUpstairsAdvisor()]),
    # COMBAT
    SequentialCompositeAdvisor(flags=flags.AdjacentToMonster, advisors=[
        SafeMeleeAttackAdvisor(),
        RandomMoveAdvisor(square_threat_tolerance=0.),
        PassiveMonsterRangedAttackAdvisor(),
        UnsafeMeleeAttackAdvisor(flags=flags.NoMoves),
        ]),
    # WEAK
    SequentialCompositeAdvisor(flags=flags.WeakWithHunger, advisors=[
        InventoryEatAdvisor(threat_tolerance=0.05),
        PrayForNutritionAdvisor(),
        ]),
    # LYCANTHROPY PUNISHED ETC
    SequentialCompositeAdvisor(flags=flags.MajorTrouble, advisors=[PrayForLesserMajorTroubleAdvisor()]),
    # DISTANT THREAT
    SequentialCompositeAdvisor(flags=flags.AmThreatened, advisors=[
        RandomMoveAdvisor(square_threat_tolerance=0.),
        HuntNearestEnemyPathAdvisor(),
        ]),
    ###### OUT OF DANGER ###### ()
    # WHEN SAFE IMPROVEMENTS
    SequentialCompositeAdvisor(flags=flags.AmSafe, advisors=[
        AnyWardrobeChangeAdvisor(),
        ReadUnidenifiedScrollAdvisor()
        ]),
    # IMPROVEMENTS
    SequentialCompositeAdvisor(advisors=[
        PickupDesirableItems(),
        EatCorpseAdvisor(),
        UnblockedWardrobeChangesAdvisor(),
        EngraveTestWandsAdvisor(),
        ]),
    # HUNT
    SequentialCompositeAdvisor(advisors=[HuntNearestWeakEnemyPathAdvisor(path_threat_tolerance=0.1)]),
    # OPEN PATHS
    SequentialCompositeAdvisor(advisors=[
        OpenClosedDoorAdvisor(),
        KickLockedDoorAdvisor(flags=flags.InDungeonsOfDoom),
        TraverseUnknownUpstairsAdvisor(),
        ]),
    # MOVE TO DESIRABLE
    SequentialCompositeAdvisor(flags=, advisors=[
        FreshCorpseMoveAdvisor(square_threat_tolerance=0.),
        DesirableObjectMoveAdvisor(square_threat_tolerance=0.),
        ]),
    # EXPLORE
    SequentialCompositeAdvisor(advisors=[SearchForSecretDoorAdvisor()]),
    RandomCompositeAdvisor(advisors={
        MostNovelMoveAdvisor(square_threat_tolerance=0.): 5,
        RandomMoveAdvisor(square_threat_tolerance=0.): 1,
        })
]

new_advisors = [
    # FREE IMPROVEMENT
    AdvisorLevel({EnhanceSkillsAdvisor(): 1,}),
    # STONING ILL ETC
    UrgentMajorTroubleAdvisorLevel({PrayWhenMajorTroubleAdvisor(): 1,}),
    # CRITICALLY INJURED
    CriticallyInjuredAdvisorLevel({WaitAdvisor(): 1,}, threat_tolerance=0.),
    CriticallyInjuredOrLifeThreatenedAdvisorLevel({GoUpstairsAdvisor(carried_threat_tolerance=0.): 1}),
    CriticallyInjuredOrLifeThreatenedAdvisorLevel({DoCombatHealingAdvisor(): 1,}),
    CriticallyInjuredOrLifeThreatenedAdvisorLevel({UseEscapeItemAdvisor(): 1,}),
    CriticallyInjuredAdvisorLevel({PrayForLowHPAdvisor(): 1,}),
    CriticallyInjuredOrLifeThreatenedAdvisorLevel({EngraveElberethAdvisor()}: 1),
    CriticallyInjuredOrLifeThreatenedAdvisorLevel({RetreatPathAdvisor(path_threat_tolerance=0.3): 1}),
    # WEAK
    WeakWithHungerAdvisorLevel({CombatEatAdvisor(): 1,}, threat_tolerance=0.05),
    # HIGHLY THREATENED
    AdvisorLevel({RetreatMoveAdvisor(): 1}, threat_threshold=0.4),
    # IN GNOMISH MINES
    GnomishMinesAdvisorLevel({GoUpstairsAdvisor(): 1,}),
    # COMBAT
    AdjacentToMonsterAdvisorLevel({SafeMeleeAttackAdvisor(): 1,}),
    # WEAK
    WeakWithHungerAdvisorLevel({EatTopInventoryAdvisor(): 1,}, threat_tolerance=0.05),
    WeakWithHungerAdvisorLevel({PrayWhenWeakAdvisor(): 1,}),
    # LYCANTHROPY PUNISHED ETC
    MajorTroubleAdvisorLevel({PrayWhenMajorTroubleAdvisor(): 1,}),
    # DISTANT THREAT
    ThreatenedAdvisorLevel({RandomMoveAdvisor(square_threat_tolerance=0.)}, no_adjacent_monsters=True), # evasive maneuvers
    ThreatenedAdvisorLevel({HuntNearestEnemyPathAdvisor(): 1}), # hunt distant monster
    ###### OUT OF DANGER ###### ()
    # WHEN SAFE IMPROVEMENTS
    SafeAdvisorLevel({AllWardrobeChangesAdvisor(): 1}),
    SafeAdvisorLevel({ReadUnidenifiedScrollAdvisor(): 1}),
    # IMPROVEMENTS
    AdvisorLevel({PickupDesirableItems()}: 1),
    AdvisorLevel({EatCorpseAdvisor()}: 1),
    AdvisorLevel({UnblockedWardrobeChangesAdvisor()}: 1),
    AdvisorLevel({EngraveTestWandsAdvisor()}: 1),
    # HUNT
    AdvisorLevel({HuntNearestWeakEnemyPathAdvisor(path_threat_tolerance=0.1): 1}),
    # OPEN PATHS
    AdvisorLevel({OpenClosedDoorAdvisor(): 1,}),
    DungeonsOfDoomAdvisorLevel({KickLockedDoorAdvisor(): 1,}),
    AdvisorLevel({TraverseUnknownUpstairsAdvisor(): 1,}),
    # MOVE TO DESIRABLE
    AdvisorLevel({FreshCorpseMoveAdvisor(square_threat_tolerance=0.): 1,}),
    AdvisorLevel({DesirableObjectMoveAdvisor(square_threat_tolerance=0.): 1,}),
    # EXPLORE
    AdvisorLevel({SearchForSecretDoorAdvisor(): 1})
    AdvisorLevel({
            MostNovelMoveAdvisor(square_threat_tolerance=0.): 5,
            RandomMoveAdvisor(square_threat_tolerance=0.): 1,
        }),
]


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