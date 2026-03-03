$version: "2"

namespace layertwo.ffsync


@documentation("FxA device management resource")
resource Device {
    operations: [RegisterDevice, ListDevices, ListAttachedClients, NotifyDevices]
}

// ============================================================================
// Register/Update Device
// ============================================================================

@http(method: "POST", uri: "/v1/account/device")
@documentation("Register a new device or update an existing device registration")
operation RegisterDevice {
    input: RegisterDeviceInput
    output: RegisterDeviceOutput
    errors: [AuthenticationException]
}

@input
structure RegisterDeviceInput {
    @documentation("Device ID (32-char hex). Omit to create, include to update.")
    id: String

    @documentation("Device display name")
    name: String

    @documentation("Device type: desktop, mobile, or tablet")
    type: String

    @documentation("Web Push callback URL")
    pushCallback: String

    @documentation("Web Push public key (URL-safe base64)")
    pushPublicKey: String

    @documentation("Web Push auth key (URL-safe base64)")
    pushAuthKey: String

    @documentation("Map of available commands to encrypted key bundles")
    availableCommands: AvailableCommandsMap
}

map AvailableCommandsMap {
    key: String
    value: String
}

@output
structure RegisterDeviceOutput {
    @required
    id: String

    name: String
    type: String
    pushCallback: String
    pushPublicKey: String
    pushAuthKey: String
    pushEndpointExpired: Boolean
    availableCommands: AvailableCommandsMap
    sessionTokenId: String
    createdAt: Long
    lastAccessTime: Long
}

// ============================================================================
// List Devices
// ============================================================================

@readonly
@http(method: "GET", uri: "/v1/account/devices")
@documentation("List all devices registered to the account")
operation ListDevices {
    input: ListDevicesInput
    output: ListDevicesOutput
    errors: [AuthenticationException]
}

@input
structure ListDevicesInput {
    @httpQuery("filterIdleDevicesTimestamp")
    @documentation("Exclude devices not accessed since this timestamp (ms)")
    filterIdleDevicesTimestamp: Long
}

@output
structure ListDevicesOutput {
    @required
    devices: DeviceList
}

list DeviceList {
    member: DeviceRecord
}

structure DeviceRecord {
    @required
    id: String

    name: String
    type: String
    isCurrentDevice: Boolean
    lastAccessTime: Long
    pushCallback: String
    pushPublicKey: String
    pushAuthKey: String
    pushEndpointExpired: Boolean
    availableCommands: AvailableCommandsMap
}

// ============================================================================
// List Attached Clients
// ============================================================================

@readonly
@http(method: "GET", uri: "/v1/account/attached_clients")
@documentation("List all attached clients (devices + OAuth sessions)")
operation ListAttachedClients {
    input: ListAttachedClientsInput
    output: ListAttachedClientsOutput
    errors: [AuthenticationException]
}

@input
structure ListAttachedClientsInput {}

@output
structure ListAttachedClientsOutput {
    @required
    clients: AttachedClientList
}

list AttachedClientList {
    member: AttachedClient
}

structure AttachedClient {
    clientId: String
    deviceId: String
    sessionTokenId: String
    refreshTokenId: String
    isCurrentSession: Boolean
    deviceType: String
    name: String
    createdTime: Long
    lastAccessTime: Long
    scope: String
    userAgent: String
    os: String
}

// ============================================================================
// Notify Devices
// ============================================================================

@http(method: "POST", uri: "/v1/account/devices/notify")
@documentation("Send a push notification to devices (no-op in self-hosted)")
operation NotifyDevices {
    input: NotifyDevicesInput
    output: NotifyDevicesOutput
    errors: [AuthenticationException]
}

@input
structure NotifyDevicesInput {}

@output
structure NotifyDevicesOutput {}
