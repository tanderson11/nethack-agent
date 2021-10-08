#from advisors import *
from  advisors import *

new_advisors = [
    # FREE IMPROVEMENT
    NameItemAdvisor(),
    EnhanceSkillsAdvisor(),
    # STONING ILL ETC
    ApplyUnicornHornAdvisor(oracle_consultation=lambda o: o.deadly_condition),
    PrayForUrgentMajorTroubleAdvisor(oracle_consultation=lambda o: o.urgent_major_trouble),
    # CRITICALLY INJURED
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.critically_injured or o.life_threatened, advisors=[
        WaitAdvisor(threat_tolerance=0.),
        #UpstairsAdvisor(), # TK square_threat_tolerance=0. once we know who is waiting on the upstairs
        DoCombatHealingAdvisor(),
        UseEscapeItemAdvisor(),
        PrayForHPAdvisor(oracle_consultation=lambda o: o.can_pray_for_hp),
        #EngraveElberethAdvisor(),
        #PathfindToSafetyAdvisor(path_threat_tolerance=0.3),
        ]),
    # FAST IMPROVEMENT
    AdjustRangedPlanDummy(),
    WieldBetterWeaponAdvisor(),
    GainSpeedFromWand(),
    # WEAK
    CombatEatAdvisor(oracle_consultation=lambda o: o.weak_with_hunger, threat_tolerance=0.05),
    # HIGHLY THREATENED
    #PathfindToSafetyAdvisor(threat_threshold=0.4, path_threat_tolerance=0.4),
    # IN GNOMISH MINES
    TakeStaircaseAdvisor(),
    # COMBAT
    ApplyUnicornHornAdvisor(oracle_consultation=lambda o: o.minor_unicorn_condition),
    #PassiveMonsterRangedAttackAdvisor(), # if you want to do it at actual range
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.adjacent_monsters > 0, advisors=[
        MeleeHoldingMonster(),
        MeleePriorityTargets(),
        ReduceThreatFromManyEnemiesWithMove(),
        SafeMeleeAttackAdvisor(),
        PassiveMonsterRangedAttackAdvisor(),
        #RandomMoveAdvisor(),
        UnsafeMeleeAttackAdvisor(oracle_consultation=lambda o: not o.have_moves),
        ]),
    #RangedAttackNuisanceMonsters(),
    #RangedAttackHighlyThreateningMonsters(),
    # WEAK
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.weak_with_hunger, advisors=[
        InventoryEatAdvisor(threat_tolerance=0.05),
        PrayForNutritionAdvisor(),
        ]),
    # LYCANTHROPY PUNISHED ETC
    PrayForLesserMajorTroubleAdvisor(oracle_consultation=lambda o: o.major_trouble),
    # DISTANT THREAT
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.am_threatened, advisors=[
        RandomMoveAdvisor(square_threat_tolerance=0.),
        HuntNearestEnemyAdvisor(), # any enemy, not weak, thus we prefer to let them come to us if we can by doing evasive moves
        ]),
    WaitAdvisor(oracle_consultation=lambda o: o.in_shop and o.blind),
    WaitAdvisor(oracle_consultation=lambda o: o.nuisance_condition and not (o.am_threatened or o.recently_damaged)),
    ###### OUT OF DANGER ###### ()
    BuyDesirableAdvisor(),
    DrinkHealingForMaxHPAdvisor(),
    DipForExcaliburAdvisor(),
    # WHEN SAFE IMPROVEMENTS
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.am_safe, advisors=[
        DropUndesirableInShopAdvisor(),
        DropShopOwnedAdvisor(),
        DropToPriceIDAdvisor(),
        DropUndesirableWantToLowerWeight(),
        AnyWardrobeChangeAdvisor(),
        IdentifyUnidentifiedScrolls(),
        IdentifyPotentiallyMagicArmorAdvisor(),
        ReadRemoveCurse(),
        ReadKnownBeneficialScrolls(),
        ReadSafeUnidentifiedScrolls(),
        #ReadUnidentifiedScrollsAdvisor()
        ]),
    # IMPROVEMENTS
    SequentialCompositeAdvisor(advisors=[
        DropUnknownOnAltarAdvisor(),
        PickupDesirableItems(),
        EatCorpseAdvisor(),
        UnblockedWardrobeChangesAdvisor(),
        EngraveTestWandsAdvisor(),
        ]),
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.low_hp and not (o.am_threatened or o.recently_damaged), advisors=[
        PathfindDesirableObjectsAdvisor(oracle_consultation=lambda o: not o.in_shop and o.character.desperate_for_food()),
        WaitAdvisor(),
    ]),
    SolveSokoban(),
    # HUNT WEAK
    HuntNearestWeakEnemyAdvisor(path_threat_tolerance=0.5),
    # OPEN PATHS
    SequentialCompositeAdvisor(advisors=[
        KickLockedDoorAdvisor(oracle_consultation=lambda o: not o.in_shop),
        OpenClosedDoorAdvisor(),
        ]),
    # MOVE TO DESIRABLE
    PathfindUnvisitedShopSquares(oracle_consultation=lambda o: o.in_shop),
    PathfindDesirableObjectsAdvisor(oracle_consultation=lambda o: not o.in_shop),
    # EXPLORE
    SearchDeadEndAdvisor(),
    UnvisitedSquareMoveAdvisor(square_threat_tolerance=0.),
    RandomCompositeAdvisor(advisors={
        MostNovelMoveAdvisor(square_threat_tolerance=0.): 10,
        RandomMoveAdvisor(square_threat_tolerance=0.): 1,
        SearchForSecretDoorAdvisor(oracle_consultation=lambda o: not o.on_warning_engraving): 4,
        TravelToDesiredEgress(): 1,
        TravelToFountainAdvisorForExcalibur(): 3,
        TravelToAltarAdvisor(): 2,
        TravelToBespokeUnexploredAdvisor(lambda o: not o.recently_damaged): 4,
    }),
    RandomMoveAdvisor(),
    FallbackSearchAdvisor(),
]