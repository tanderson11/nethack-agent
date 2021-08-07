#from advisors import *
from  new_advisors import *

new_advisors = [
    # FREE IMPROVEMENT
    EnhanceSkillsAdvisor(),
    # STONING ILL ETC
    PrayForUrgentMajorTroubleAdvisor(oracle_consultation=lambda o: o.UrgentMajorTrouble),
    # CRITICALLY INJURED
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.CriticallyInjured or o.LifeThreatened, advisors=[ # oracle_consultation=dumb, doesn't work
        WaitAdvisor(threat_tolerance=0.),
        GoUpstairsAdvisor(carried_threat_tolerance=0.),
        DoCombatHealingAdvisor(),
        UseEscapeItemAdvisor(),
        PrayForHPAdvisor(),
        #EngraveElberethAdvisor(),
        #PathfindToSafetyAdvisor(path_threat_tolerance=0.3),
        ]),
    # WEAK
    CombatEatAdvisor(oracle_consultation=lambda o: o.WeakWithHunger, threat_tolerance=0.05),
    # HIGHLY THREATENED
    PathfindToSafetyAdvisor(threat_threshold=0.4),
    # IN GNOMISH MINES
    GoUpstairsAdvisor(oracle_consultation=lambda o: o.InGnomishMines),
    # COMBAT
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.AdjacentToMonster, advisors=[
        SafeMeleeAttackAdvisor(),
        RandomMoveAdvisor(square_threat_tolerance=0.),
        PassiveMonsterRangedAttackAdvisor(),
        UnsafeMeleeAttackAdvisor(oracle_consultation=lambda o: o.NoMoves),
        ]),
    # WEAK
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.WeakWithHunger, advisors=[
        InventoryEatAdvisor(threat_tolerance=0.05),
        PrayForNutritionAdvisor(),
        ]),
    # LYCANTHROPY PUNISHED ETC
    PrayForLesserMajorTroubleAdvisor(oracle_consultation=lambda o: o.MajorTrouble),
    # DISTANT THREAT
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.AmThreatened, advisors=[
        HuntNearestEnemyPathAdvisor(),
        RandomMoveAdvisor(square_threat_tolerance=0.),
        ]),
    ###### OUT OF DANGER ###### ()
    # WHEN SAFE IMPROVEMENTS
    SequentialCompositeAdvisor(oracle_consultation=lambda o: o.AmSafe, advisors=[
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
    HuntNearestWeakEnemyPathAdvisor(path_threat_tolerance=0.1),
    # OPEN PATHS
    SequentialCompositeAdvisor(advisors=[
        OpenClosedDoorAdvisor(),
        KickLockedDoorAdvisor(oracle_consultation=lambda o: o.InDungeonsOfDoom),
        TraverseUnknownUpstairsAdvisor(),
        ]),
    # MOVE TO DESIRABLE
    SequentialCompositeAdvisor(advisors=[
        FreshCorpseMoveAdvisor(square_threat_tolerance=0.),
        DesirableObjectMoveAdvisor(square_threat_tolerance=0.),
        ]),
    # EXPLORE
    RandomCompositeAdvisor(advisors={
        MostNovelMoveAdvisor(square_threat_tolerance=0.): 5,
        SearchForSecretDoorAdvisor(): 3,
        RandomMoveAdvisor(square_threat_tolerance=0.): 1,
        })
]