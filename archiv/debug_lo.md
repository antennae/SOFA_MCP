T: With the help of this MCP, debug @RobSouple-SOFA/project.py
4m25
  ┌─────┬──────────┬─────────────────────┬──────────────────────────────────────────────────────────────────────────┐
  │  #  │ Severity │      Location       │                                  Issue                                   │
  ├─────┼──────────┼─────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ 1   │ Critical │ projet.py:227       │ spc_HG.value = [0.0] always overrides pressure ramp to zero              │
  ├─────┼──────────┼─────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ 2   │ High     │ projet.py:154       │ robot_bas double-parented under simulation                               │
  ├─────┼──────────┼─────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ 3   │ High     │ projet.py:156–157   │ FixedProjectiveConstraint commented out — robot has no fixed base        │
  ├─────┼──────────┼─────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ 4   │ Medium   │ projet.py:77        │ BlockGaussSeidelConstraintSolver deprecated, use GenericConstraintSolver │
  ├─────┼──────────┼─────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ 5   │ Low      │ projet.py:151       │ SparseLDLSolver scalar template; use CompressedRowSparseMatrixMat3x3d    │
  ├─────┼──────────┼─────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ 6   │ Medium   │ scene_writer.py:153 │ summarize_scene subprocess crashes: _tree_has_class not in template      │
  └─────┴──────────┴─────────────────────┴──────────────────────────────────────────────────────────────────────────┘
T: Fix 1

    fixed

T: Now I can run the scene, but as simulation progress and pressure increase, it will start to sliding into the floor after 10 steps, and           
completely fly off at step 14 
56s :
    please fix 3 

T: no, i think that is not the problem. Please comment out this constraint. Then try to run 20 steps, then see what you can find. because I think   
the problem is elsewhere because the deformation of the robot is so massive at around 13, 14  steps

    tried a few things, even suspect that he was running the wrong file
    stuck after 16m

T: It's getting worse (he changed the FEM method to large), it diverge in 10 steps 

    he decide to remove the floor. but it seems stuck again

T: So try to run 20 steps and see what happens

T: Is it stuck ? restart the server and then retry  

    He found out remove the floor -> no problem
    increase contact stiffness from 100 to 1e6 -> not work
    Change contact stiffness back to 100, try change response method in CollisionResponse
    He changed to FrictionContact, it didn't exist, it have difficulty finding what to set, he try to look for 

    Note : he should get a list of options but somehow he did grasp those list there, he is querry component etc 
    I know he cannot find it by querry componnent so I interrupted and give him this hint (from running the scene).

T: In fact, for the method in CollisionResponse :  Option list is: ["AugmentedLagrangianResponseConstraint", "FrictionContactConstraint",           
"PenalityContactForceField", "RayContact", "StickContactConstraint", "StickContactForceField"]

    Changed and fixed (i think)


  Summary of all fixes applied to projet.py:

  ┌─────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │   Fix   │                                                              Change                                                              │
  ├─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Bug 1   │ spc_HG.value = [0.0] → [self.sp_HG] — pressure ramp was never applied                                                            │
  ├─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Bug 2   │ Removed simulation.addChild(robot_bas) — double-parenting                                                                        │
  ├─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Bug 4   │ BlockGaussSeidelConstraintSolver → NNCGConstraintSolver                                                                          │
  ├─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Bug 5   │ SparseLDLSolver template="CompressedRowSparseMatrixd" → Mat3x3d                                                                  │
  ├─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Root    │ CollisionResponse response='PenalityContactForceField' → 'FrictionContactConstraint' — penalty contact is incompatible with      │
  │ cause   │ FreeMotionAnimationLoop; the Lagrangian constraint-based contact routes floor collision through the NNCG solver, keeping         │
  │         │ everything stable                                                                                                                │
  └─────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

