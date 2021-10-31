#from advisors import *
from  advisors import *

new_advisors = [
    # Name starting pet
    NameStartingPet(),
    # No-time recon
    NearLook(),
    # FREE IMPROVEMENT
    NameItemAdvisor(),
    NameWishItemAdvisor(),
    EnhanceSkillsAdvisor(),
    # SPECIAL TIME SENSITIVE OPERATIONS
    SpecialItemFactAdvisor(),
    # STONING ILL ETC
    ApplyUnicornHornAdvisor(oracle_consultation=lambda o: o.deadly_condition),
    PrayForUrgentMajorTroubleAdvisor(oracle_consultation=lambda o: o.urgent_major_trouble),
    # CRITICALLY INJURED
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.critically_injured or o.life_threatened, advisors=[
        WaitForHPAdvisor(threat_tolerance=0.),
        #UpstairsAdvisor(), # TK square_threat_tolerance=0. once we know who is waiting on the upstairs
        DoCombatHealingAdvisor(),
        UseEscapeItemAdvisor(),
        WaitForHPAdvisor(oracle_consultation=lambda o: o.on_elbereth),
        PrayForHPAdvisor(oracle_consultation=lambda o: o.can_pray_for_hp),
        EngraveElberethAdvisor(),
        #PathfindToSafetyAdvisor(path_threat_tolerance=0.3),
        ]),
    # ADJUST/ABORT SUBROUTINES
    AdjustEscapePlanDummy(),
    AdjustRangedPlanDummy(),
    # FAST IMPROVEMENT
    WieldBetterWeaponAdvisor(),
    GainSpeedFromWand(),
    # WEAK
    CombatEatAdvisor(oracle_consultation=lambda o: o.weak_with_hunger),
    # HIGHLY THREATENED
    TakeStaircaseAdvisor(),
    PathfindTactical(),
    # COMBAT
    ApplyUnicornHornAdvisor(oracle_consultation=lambda o: o.minor_unicorn_condition),
    #PassiveMonsterRangedAttackAdvisor(), # if you want to do it at actual range
    RetameCarnivorePet(),
    RetameHerbivorePet(),
    DrinkHealingPotionWhenLow(),
    CastHealing(),
    WaitAdvisor(oracle_consultation=lambda o: o.very_low_hp and o.on_elbereth),
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.adjacent_monsters > 0, advisors=[
        TameHerbivores(),
        TameCarnivores(),
        BlindFearfulWithCamera(),
        EngraveElberethAdvisor(oracle_consultation=lambda o: o.very_low_hp),
        MeleeRangedAttackIfPreferred(),
        MeleeHoldingMonster(),
        MeleePriorityTargets(),
    ]),
    SafeMeleeAttackAdvisor(),
    PassiveMonsterRangedAttackAdvisor(),
    RangedAttackFearfulMonsters(),
    #RangedAttackHighlyThreateningMonsters(),
    # WEAK
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.weak_with_hunger, advisors=[
        InventoryEatAdvisor(),
        PrayForNutritionAdvisor(),
        ]),
    # LYCANTHROPY PUNISHED ETC
    PrayForLesserMajorTroubleAdvisor(oracle_consultation=lambda o: o.major_trouble),
    # Stuck and gotta bust out
    StuckChangeOfSquare(),
    #EngraveElberethStuckByMonster(),
    UnsafeMeleeAttackAdvisor(oracle_consultation=lambda o: o.adjacent_monsters > 0 and not o.have_moves),
    # HUNT WEAK
    HuntNearestWeakEnemyAdvisor(),
    # DISTANT THREAT
    RandomCompositeAdvisor(oracle_consultation=lambda o: o.am_threatened, advisors={
        RandomMoveAdvisor(square_threat_tolerance=0.): 95,
        HuntNearestEnemyAdvisor(): 5, # any enemy, not weak, thus we prefer to let them come to us if we can by doing evasive moves
    }),
    ConditionWaitAdvisor(oracle_consultation=lambda o: o.in_shop and o.blind),
    ConditionWaitAdvisor(oracle_consultation=lambda o: o.nuisance_condition and not (o.am_threatened or o.recently_damaged)),
    ###### OUT OF DANGER ###### ()
    BuyDesirableAdvisor(),
    DrinkHealingForMaxHPAdvisor(),
    DrinkGainAbility(),
    DrinkGainLevel(),
    DipForExcaliburAdvisor(),
    # WHEN SAFE IMPROVEMENTS
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.am_safe, advisors=[
        ChargeWandOfWishing(),
        ZapWandOfWishing(),
        WrestWandOfWishing(),
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
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.low_hp and not (o.am_threatened), advisors=[
        PathfindDesirableObjectsAdvisor(oracle_consultation=lambda o: not o.in_shop and o.character.desperate_for_food()),
        WaitForHPAdvisor(oracle_consultation=lambda o: not o.desperate_for_food),
    ]),
    PathfindObivousMimicsSokoban(),
    PathfindInvisibleMonstersSokoban(),
    RangedAttackInvisibleInSokoban(),
    SolveSokoban(),
    PathfindSokobanSquare(),
    TravelToSokobanSquare(),
    HealerHealingPotionRollout(),
    # OPEN PATHS
    SequentialCompositeAdvisor(advisors=[
        KickLockedDoorAdvisor(oracle_consultation=lambda o: not o.in_shop),
        OpenClosedDoorAdvisor(),
        ]),
    # MOVE TO DESIRABLE
    PathfindUnvisitedShopSquares(oracle_consultation=lambda o: o.in_shop),
    PathfindDesirableObjectsAdvisor(oracle_consultation=lambda o: not o.in_shop),
    # EXPLORE
    SearchWithStethoscope(oracle_consultation=lambda o:o.have_free_stethoscope_action),
    SearchDeadEndsWithStethoscope(),
    SearchDeadEndAdvisor(oracle_consultation=lambda o: not o.have_stethoscope),
    UnvisitedSquareMoveAdvisor(),
    RandomCompositeAdvisor(advisors={
        MostNovelMoveAdvisor(): 10,
        RandomMoveAdvisor(): 1,
        SearchForSecretDoorAdvisor(oracle_consultation=lambda o: not o.on_warning_engraving and not o.have_stethoscope): 4,
        TravelToDesiredEgress(): 1,
        TravelToFountainAdvisorForExcalibur(): 3,
        TravelToAltarAdvisor(): 2,
        TravelToBespokeUnexploredAdvisor(lambda o: not o.recently_damaged): 4,
    }),
    RandomMoveAdvisor(),
    FallbackSearchAdvisor(),
]