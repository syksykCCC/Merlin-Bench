# Protocol

Submit exactly one event at sequence zero with kind
`homomorphism.assignment`, no artifact references, and payload
`{"mapping": [...]}`. Arthur checks the complete mapping against the public
lists and all public source edges. Every response is terminal.
