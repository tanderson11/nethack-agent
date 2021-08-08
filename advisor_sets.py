#from advisors import *
from  new_advisors import *

new_advisors = [
    # FREE IMPROVEMENT
    EnhanceSkillsAdvisor(),
    # STONING ILL ETC
    PrayForUrgentMajorTroubleAdvisor(oracle_consultation=lambda o: o.urgent_major_trouble),
    # CRITICALLY INJURED
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.critically_injured or o.life_threatened, advisors=[ # oracle_consultation=dumb, doesn't work
        WaitAdvisor(threat_tolerance=0.),
        UpstairsAdvisor(), # TK square_threat_tolerance=0. once we know who is waiting on the upstairs
        DoCombatHealingAdvisor(),
        UseEscapeItemAdvisor(),
        PrayForHPAdvisor(oracle_consultation=lambda o: o.can_pray_for_hp),
        #EngraveElberethAdvisor(),
        #PathfindToSafetyAdvisor(path_threat_tolerance=0.3),
        ]),
    # WEAK
    CombatEatAdvisor(oracle_consultation=lambda o: o.weak_with_hunger, threat_tolerance=0.05),
    # HIGHLY THREATENED
    #PathfindToSafetyAdvisor(threat_threshold=0.4, path_threat_tolerance=0.4),
    # IN GNOMISH MINES
    UpstairsAdvisor(oracle_consultation=lambda o: o.in_gnomish_mines),
    # COMBAT
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.adjacent_monsters > 0, advisors=[
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
        ]),
    ###### OUT OF DANGER ###### ()
    # WHEN SAFE IMPROVEMENTS
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.am_safe, advisors=[
        AnyWardrobeChangeAdvisor(),
        #ReadUnidenifiedScrollAdvisor()
        ]),
    # IMPROVEMENTS
    SequentialCompositeAdvisor(advisors=[
        PickupDesirableItems(),
        EatCorpseAdvisor(),
        UnblockedWardrobeChangesAdvisor(),
        #EngraveTestWandsAdvisor(),
        ]),
    # HUNT WEAK
    HuntNearestWeakEnemyAdvisor(path_threat_tolerance=0.1),
    # OPEN PATHS
    SequentialCompositeAdvisor(advisors=[
        KickLockedDoorAdvisor(),
        OpenClosedDoorAdvisor(),
        TraverseUnknownUpstairsAdvisor(),
        ]),
    GoDownstairsAdvisor(),
    # MOVE TO DESIRABLE
    SequentialCompositeAdvisor(advisors=[
        #FreshCorpseMoveAdvisor(square_threat_tolerance=0.),
        #DesirableObjectMoveAdvisor(square_threat_tolerance=0.),
        ]),
    # EXPLORE
    RandomCompositeAdvisor(advisors={
        MostNovelMoveAdvisor(square_threat_tolerance=0.): 10,
        SearchForSecretDoorAdvisor(oracle_consultation=lambda o: not o.on_warning_engraving): 6,
        RandomMoveAdvisor(square_threat_tolerance=0.): 2,
        TravelToDownstairsAdvisor(): 1,
        }),
    FallbackSearchAdvisor(),
]