# secrets/

Local secret files mounted as Docker secrets. Everything in this directory except
this README is git-ignored.

Generate development secrets with:

    ./infrastructure/scripts/init-secrets.sh

| File                  | Used by                      | Purpose                                   |
|-----------------------|------------------------------|-------------------------------------------|
| `db_root_password`    | `db`, `provisioner` only     | MariaDB root password (site creation)     |
| `hub_admin_password`  | `provisioner` (hub creation) | Administrator password of the hub site    |
| `demo_password`       | `noria.sh seed` only         | Password of all demo users (dev only)     |

In production, provide these via your secret manager and mount them at the same
paths; never put them in `.env` or in image build arguments.
