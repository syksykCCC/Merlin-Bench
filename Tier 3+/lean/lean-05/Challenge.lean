import Init
namespace Challenge
inductive Cmd where
  | skip
  | put : Nat → Cmd
  | raise : Nat → Cmd
  | seq : Cmd → Cmd → Cmd
  | catch : Cmd → (Nat → Cmd) → Cmd
  | finally : Cmd → Cmd → Cmd
  | loop : (Nat → Bool) → Cmd → Cmd
inductive Outcome where
  | normal : Nat → Outcome
  | thrown : Nat → Nat → Outcome

def store : Outcome → Nat
  | .normal s => s
  | .thrown _ s => s

def resume : Outcome → Nat → Outcome
  | .normal _, s => .normal s
  | .thrown e _, s => .thrown e s

inductive Exec : Cmd → Nat → Outcome → Prop where
  | skip {s} : Exec .skip s (.normal s)
  | put {s n} : Exec (.put n) s (.normal n)
  | raise {s e} : Exec (.raise e) s (.thrown e s)
  | seqNormal {a b s t o} : Exec a s (.normal t) → Exec b t o → Exec (.seq a b) s o
  | seqThrown {a b s e t} : Exec a s (.thrown e t) → Exec (.seq a b) s (.thrown e t)
  | catchNormal {a h s t} : Exec a s (.normal t) → Exec (.catch a h) s (.normal t)
  | catchThrown {a h s e t o} : Exec a s (.thrown e t) → Exec (h e) t o → Exec (.catch a h) s o
  | finallyNormal {a b s o t} : Exec a s o → Exec b (store o) (.normal t) → Exec (.finally a b) s (resume o t)
  | finallyThrown {a b s o e t} : Exec a s o → Exec b (store o) (.thrown e t) → Exec (.finally a b) s (.thrown e t)
  | loopFalse {b c s} : b s = false → Exec (.loop b c) s (.normal s)
  | loopTrue {b c s o} : b s = true → Exec (.seq c (.loop b c)) s o → Exec (.loop b c) s o

inductive Frame where
  | seq : Cmd → Frame
  | catch : (Nat → Cmd) → Frame
  | finally : Cmd → Frame
  | pending : Outcome → Frame
inductive State where
  | run : Cmd → Nat → List Frame → State
  | done : Outcome → List Frame → State
inductive Step : State → State → Prop where
  | skip {s k} : Step (.run .skip s k) (.done (.normal s) k)
  | put {s n k} : Step (.run (.put n) s k) (.done (.normal n) k)
  | raise {s e k} : Step (.run (.raise e) s k) (.done (.thrown e s) k)
  | seq {a b s k} : Step (.run (.seq a b) s k) (.run a s (.seq b :: k))
  | seqNormal {s b k} : Step (.done (.normal s) (.seq b :: k)) (.run b s k)
  | seqThrown {e s b k} : Step (.done (.thrown e s) (.seq b :: k)) (.done (.thrown e s) k)
  | catch {a h s k} : Step (.run (.catch a h) s k) (.run a s (.catch h :: k))
  | catchNormal {s h k} : Step (.done (.normal s) (.catch h :: k)) (.done (.normal s) k)
  | catchThrown {e s h k} : Step (.done (.thrown e s) (.catch h :: k)) (.run (h e) s k)
  | finally {a b s k} : Step (.run (.finally a b) s k) (.run a s (.finally b :: k))
  | cleanup {o b k} : Step (.done o (.finally b :: k)) (.run b (store o) (.pending o :: k))
  | resume {o t k} : Step (.done (.normal t) (.pending o :: k)) (.done (resume o t) k)
  | override {o e t k} : Step (.done (.thrown e t) (.pending o :: k)) (.done (.thrown e t) k)
  | loopFalse {b c s k} : b s = false → Step (.run (.loop b c) s k) (.done (.normal s) k)
  | loopTrue {b c s k} : b s = true → Step (.run (.loop b c) s k) (.run (.seq c (.loop b c)) s k)
inductive Steps : State → State → Prop where
  | refl (s) : Steps s s
  | next {a b c} : Step a b → Steps b c → Steps a c

-- Cleanup always runs; a cleanup exception overrides a pending exception.
-- Both directions, arbitrary nested handlers, loops, states and outcomes.
def Target : Prop := ∀ c s o, Exec c s o ↔ Steps (.run c s []) (.done o [])
end Challenge
