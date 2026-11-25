# Protocol

Submit exactly one `set_cover.selection` event at sequence 0 with no artifacts.
Its payload contains only a `set_ids` array of distinct public set IDs. Arthur
accepts exactly when their total public weight is within `budget` and their
union covers every element from 1 through `num_elements`.
