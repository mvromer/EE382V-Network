import QtQuick 2.11
import QtQuick.Controls 1.4
import QtQuick.Controls 2.4 as Controls2
import QtQuick.Controls.Styles 1.4
import QtQuick.Layouts 1.11

import Chatter.Client 1.0

ApplicationWindow {
    id: clientWindow
    width: 800
    height: 600
    visible: true
    title: "Chatter Client"

    statusBar: StatusBar {
        RowLayout {
            anchors.fill: parent
            Label {
                text: "Chatter Client"
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            TextArea {
                Layout.fillWidth: true
                font.pointSize: 10
                readOnly: true
                enabled: appModel.clientStatus == AppModel.Connected
                textFormat: TextEdit.RichText
                text: appModel.chatBuffer
            }

            ColumnLayout {
                width: 300
                spacing: 0

                Controls2.Frame {
                    Layout.fillWidth: true

                    GridLayout {
                        anchors.fill: parent
                        columns: 2
                        rows: 4

                        Label {
                            text: "Screen name"
                        }

                        TextField {
                            id: screenNameInput
                            Layout.fillWidth: true
                            text: appModel.screenName
                            enabled: appModel.clientStatus == AppModel.Disconnected

                            Binding {
                                target: appModel
                                property: "screenName"
                                value: screenNameInput.text
                            }
                        }

                        Label {
                            text: "Server address"
                        }

                        TextField {
                            id: serverAddressInput
                            Layout.fillWidth: true
                            text: appModel.serverAddress
                            enabled: appModel.clientStatus == AppModel.Disconnected

                            Binding {
                                target: appModel
                                property: "serverAddress"
                                value: serverAddressInput.text
                            }
                        }

                        Label {
                            text: "Server port"
                        }

                        TextField {
                            id: serverPortInput
                            Layout.fillWidth: true
                            text: appModel.serverPort
                            enabled: appModel.clientStatus == AppModel.Disconnected

                            Binding {
                                target: appModel
                                property: "serverPort"
                                value: serverPortInput.text
                            }
                        }

                        RowLayout {
                            Layout.row: 3
                            Layout.column: 1
                            Layout.fillWidth: true

                            Button {
                                text: "Connect"
                                enabled: appModel.clientStatus == AppModel.Disconnected
                                onClicked: appModel.connect_client()
                            }

                            Button {
                                text: "Disconnect"
                                enabled: appModel.clientStatus == AppModel.Connected
                                onClicked: appModel.disconnect_client()
                            }
                        }
                    }
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    frameVisible: true
                    verticalScrollBarPolicy: Qt.ScrollBarAlwaysOn

                    ListView {
                        model: appModel.chatMembers
                        delegate: Text { text: model.display }
                    }
                }
            }
        }

        TextField {
            id: messageInput
            Layout.fillWidth: true
            enabled: appModel.clientStatus == AppModel.Connected
            onAccepted: appModel.send_chat_message( text )

            Connections {
                target: appModel
                onChatBufferChanged: messageInput.remove( 0, messageInput.text.length )
            }
        }
    }

    onClosing: {
        if( !appModel.clientStopped ) {
            close.accepted = false
            appModel.stop_client()
        }
    }

    Connections {
        target: appModel
        onClientStoppedChanged: clientWindow.close()
    }
}
