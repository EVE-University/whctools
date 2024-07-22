# WHC Tools App

An application designed to facilitate membership requests to join the WHC.

## Settings

Here's a list of available settings for this app. These settings can be configured by adding them to your AA settings file (local.py).

### Note

> All settings are optional, and the app will use the documented default settings if they are not overridden.

- **WHCTOOLS_TRANSIENT_REJECT**:
  - *Description*: Rejection timer in minutes for withdrawing an application.
  - *Default*: `WHCTOOLS_TRANSIENT_REJECT = 2`

- **WHCTOOLS_SHORT_REJECT**:
  - *Description*: Rejection timer in days for being rejected for a skill check during the applying stage.
  - *Default*: `WHCTOOLS_SHORT_REJECT = 5`

- **WHCTOOLS_MEDIUM_REJECT**:
  - *Description*: Rejection timer in days for being rejected for any other reason during the applying stage.
  - *Default*: `WHCTOOLS_MEDIUM_REJECT = 30`

- **WHCTOOLS_LARGE_REJECT**:
  - *Description*: Rejection timer in days for being kicked from the community.
  - *Default*: `WHCTOOLS_LARGE_REJECT = 356`

- **WHCTOOLS_LIMIT_TO_ALLIANCES**:
  - *Description*: Limits applications to ACLs to alliance IDs defined in WHCTOOLS_ALLIANCES
  - *Default*: `WHCTOOLS_LIMIT_TO_ALLIANCES = False`

- **WHCTOOLS_ALLIANCES**:
  - *Description*: Alliance IDs that are allowed to apply ACLs controlled by this tool
  - *Default*: `WHCTOOLS_ALLIANCES = [937872513, 99010193]`
