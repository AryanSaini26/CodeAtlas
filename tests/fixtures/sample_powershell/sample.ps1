# Sample PowerShell file for parser tests.

function Get-Greeting {
    param(
        [string]$Name,
        [string]$Language = "English"
    )
    Write-Output "Hello, $Name!"
}

# Process user data
function Set-UserConfig {
    param([hashtable]$Config)
    Write-Host "Applying config..."
    Apply-Settings $Config
}

class UserService {
    [string]$BaseUrl

    UserService([string]$url) {
        $this.BaseUrl = $url
    }

    [string] GetUser([int]$Id) {
        return "$($this.BaseUrl)/users/$Id"
    }

    [void] DeleteUser([int]$Id) {
        Write-Host "Deleting user $Id"
    }
}

class ConfigManager {
    [hashtable]$Settings

    ConfigManager() {
        $this.Settings = @{}
    }

    [void] Load([string]$Path) {
        $this.Settings = Get-Content $Path | ConvertFrom-Json
    }
}
