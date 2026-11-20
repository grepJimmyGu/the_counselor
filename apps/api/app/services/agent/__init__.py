"""The portfolio agent: a monitor that finds things, and a chat that explains them.

Three rules hold everywhere in this package.

1. Code computes, the model narrates. Every number an insight or a chat
   answer carries comes from a function here or from an existing service.
   The model is never asked to do arithmetic or to recall a price.
2. The agent drafts, the user decides. Nothing here places an order. An
   insight may carry an `action` the app can open, such as an order ticket
   with a symbol and a size filled in; sending it is the user's tap.
3. It reports what happened under rules the user set. It does not predict,
   and its wording carries no "should".
"""
