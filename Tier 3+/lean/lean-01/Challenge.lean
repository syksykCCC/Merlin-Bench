import AMBenchPrelude

namespace Challenge

abbrev Store := Nat → Nat
abbrev Entry := Nat × Nat
abbrev Journal := List Entry

def write (s : Store) (key value : Nat) : Store :=
  fun query => if query = key then value else s query

-- Generic point-update facts; no journal or refinement lemmas are supplied.
abbrev StoreEq (s t : Store) : Prop := ∀ key, s key = t key

theorem write_same (s : Store) (key value : Nat) : write s key value key = value :=
  if_pos rfl

theorem write_other (s : Store) (key value query : Nat) (h : query ≠ key) :
    write s key value query = s query := if_neg h

theorem write_congr {s t : Store} (h : StoreEq s t) (key value : Nat) :
    StoreEq (write s key value) (write t key value) := by
  intro query
  cases Nat.decEq query key with
  | isTrue eq => cases eq; exact Eq.trans (write_same s key value) (Eq.symm (write_same t key value))
  | isFalse ne =>
    exact Eq.trans (write_other s key value query ne) (Eq.trans (h query) (Eq.symm (write_other t key value query ne)))

def lookup : Journal → Nat → Option Nat
  | [], _ => none
  | (key, value) :: rest, query => if query = key then some value else lookup rest query

def remember (key old : Nat) (journal : Journal) : Journal :=
  match lookup journal key with
  | some _ => journal
  | none => (key, old) :: journal

def merge : Journal → Journal → Journal
  | [], parent => parent
  | (key, old) :: rest, parent => merge rest (remember key old parent)

def undo (journal : Journal) (s : Store) : Store :=
  fun query => match lookup journal query with
    | some old => old
    | none => s query

inductive Command where
  | put (key value : Nat)
  | beginTxn
  | commit
  | rollback

structure SpecState where
  current : Store
  snapshots : List Store

structure ImplState where
  current : Store
  journals : List Journal

def specStep (command : Command) (s : SpecState) : SpecState :=
  match command with
  | .put key value => ⟨write s.current key value, s.snapshots⟩
  | .beginTxn => ⟨s.current, s.current :: s.snapshots⟩
  | .commit => ⟨s.current, s.snapshots.drop 1⟩
  | .rollback => match s.snapshots with
    | [] => s
    | previous :: rest => ⟨previous, rest⟩

def implStep (command : Command) (s : ImplState) : ImplState :=
  match command with
  | .put key value =>
    let updated := write s.current key value
    match s.journals with
    | [] => ⟨updated, []⟩
    | journal :: rest => ⟨updated, (remember key (s.current key) journal) :: rest⟩
  | .beginTxn => ⟨s.current, [] :: s.journals⟩
  | .commit => match s.journals with
    | [] => s
    | [_] => ⟨s.current, []⟩
    | child :: parent :: rest => ⟨s.current, (merge child parent) :: rest⟩
  | .rollback => match s.journals with
    | [] => s
    | journal :: rest => ⟨undo journal s.current, rest⟩

def specRun : List Command → SpecState → SpecState
  | [], s => s
  | command :: rest, s => specRun rest (specStep command s)

def implRun : List Command → ImplState → ImplState
  | [], s => s
  | command :: rest, s => implRun rest (implStep command s)

def initialSpec : SpecState := ⟨fun _ => 0, []⟩
def initialImpl : ImplState := ⟨fun _ => 0, []⟩

def Target : Prop :=
  ∀ commands : List Command, ∀ key : Nat,
    (implRun commands initialImpl).current key =
      (specRun commands initialSpec).current key

end Challenge
