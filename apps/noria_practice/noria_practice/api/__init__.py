"""Noria practice-hub API consumed by the Noria frontend.

Every endpoint authenticates the session user and authorizes through
`noria_practice.authz` before touching data. Hub DocTypes are not exposed via
/api/resource (System Manager permissions only).
"""
