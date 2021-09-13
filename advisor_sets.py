#from advisors import *
from  advisors import *

new_advisors = [
    # FREE IMPROVEMENT
    EnhanceSkillsAdvisor(),
    # STONING ILL ETC
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
    # WEAPON IMPROVEMENT
    WieldBetterWeaponAdvisor(),
    # WEAK
    CombatEatAdvisor(oracle_consultation=lambda o: o.weak_with_hunger, threat_tolerance=0.05),
    # HIGHLY THREATENED
    #PathfindToSafetyAdvisor(threat_threshold=0.4, path_threat_tolerance=0.4),
    # IN GNOMISH MINES
    TakeStaircaseAdvisor(),
    # COMBAT
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.adjacent_monsters > 0, advisors=[
        MeleeHoldingMonsterAdvisor(),
        SafeMeleeAttackAdvisor(),
        RandomMoveAdvisor(square_threat_tolerance=0.),
        PassiveMonsterRangedAttackAdvisor(),
        UnsafeMeleeAttackAdvisor(oracle_consultation=lambda o: not o.have_moves),
        ]),
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
        RandomMoveAdvisor(), # sometimes we can't find our way to the enemy and we can't get out of threat
        ]),
    ###### OUT OF DANGER ###### ()
    WaitAdvisor(oracle_consultation=lambda o: (o.low_hp or o.nuisance_condition) and not (o.am_threatened or o.recently_damaged)),
    # WHEN SAFE IMPROVEMENTS
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.am_safe, advisors=[
        AnyWardrobeChangeAdvisor(),
        IdentifyPotentiallyMagicArmorAdvisor(),
        ReadKnownBeneficialScrolls(),
        #ReadUnidentifiedScrollsAdvisor()
        ]),
    # IMPROVEMENTS
    SequentialCompositeAdvisor(advisors=[
        PickupDesirableItems(),
        EatCorpseAdvisor(),
        UnblockedWardrobeChangesAdvisor(),
        EngraveTestWandsAdvisor(),
        ]),
    # HUNT WEAK
    HuntNearestWeakEnemyAdvisor(path_threat_tolerance=0.5),
    # OPEN PATHS
    SequentialCompositeAdvisor(advisors=[
        KickLockedDoorAdvisor(),
        OpenClosedDoorAdvisor(),
        ]),
    # MOVE TO DESIRABLE
    PathfindDesirableObjectsAdvisor(),
    # EXPLORE
    SearchDeadEndAdvisor(),
    UnvisitedSquareMoveAdvisor(square_threat_tolerance=0.),
    RandomCompositeAdvisor(advisors={
        MostNovelMoveAdvisor(square_threat_tolerance=0.): 10,
        RandomMoveAdvisor(square_threat_tolerance=0.): 2,
        SearchForSecretDoorAdvisor(oracle_consultation=lambda o: not o.on_warning_engraving): 6,
        # Need to somehow deal with the fact that this takes us places we know we don't want to go
        # like repeatedly back to warning-engraved doors. Or into shops.
        # TravelToUnexploredSquareAdvisor(): 2,
        TravelToDesiredEgress(): 1,
        #TravelToBespokeUnexploredAdvisor(lambda o: not o.recently_damaged): 1,
    }),
    FallbackSearchAdvisor(),
]