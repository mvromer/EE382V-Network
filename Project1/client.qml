import QtQuick 2.11
import QtQuick.Controls 1.4
import QtQuick.Controls 2.4 as Controls2
import QtQuick.Controls.Styles 1.4
import QtQuick.Layouts 1.11

ApplicationWindow {
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
                readOnly: true
                text: "The quick brown fox"
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
                            Layout.fillWidth: true
                            text: appModel.screenName
                        }

                        Label {
                            text: "Server address"
                        }

                        TextField {
                            Layout.fillWidth: true
                            text: appModel.serverAddress
                        }

                        Label {
                            text: "Server port"
                        }

                        TextField {
                            Layout.fillWidth: true
                            text: appModel.serverPort
                        }

                        RowLayout {
                            Layout.row: 3
                            Layout.column: 1
                            Layout.fillWidth: true

                            Button {
                                text: "Connect"
                            }

                            Button {
                                text: "Disconnect"
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
                    }
                }
            }
        }

        TextField {
            Layout.fillWidth: true
        }
    }
}
