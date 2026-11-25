# Protocol

Submit exactly one `closest_vector.coefficients` event at sequence 0 with no
artifacts. Its payload contains only the ordered `coefficients` array. Arthur
checks coefficient bounds and the public squared-distance inequality using
exact integers.
