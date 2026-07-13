import Foundation
import UIKit
import Capacitor

#if canImport(RoomPlan)
import RoomPlan

/// Multi-room structure capture: scan room → next room → finish structure.
final class StructureCapturePresenter: NSObject, RoomCaptureViewDelegate, RoomCaptureSessionDelegate {
    private let call: CAPPluginCall
    private let structureLabel: String
    private var captureViewController: UIViewController?
    private var captureView: RoomCaptureView?
    private let sessionConfig = RoomCaptureSession.Configuration()
    private var onFinished: (() -> Void)?
    private var completed = false

    private var capturedRooms: [CapturedRoom] = []
    private var roomLabels: [String] = []
    private var roomSections: [String?] = []
    private var roomCounter = 1

    init(call: CAPPluginCall, structureLabel: String, onFinished: (() -> Void)? = nil) {
        self.call = call
        self.structureLabel = structureLabel
        self.onFinished = onFinished
        super.init()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func encode(with coder: NSCoder) {}

    func present(from viewController: UIViewController) {
        presentCaptureUI(from: viewController, title: "Room \(roomCounter)")
    }

    private func presentCaptureUI(from viewController: UIViewController, title: String) {
        let captureVC = UIViewController()
        captureVC.modalPresentationStyle = .fullScreen
        captureVC.view.backgroundColor = .black

        let captureView = RoomCaptureView(frame: .zero)
        captureView.translatesAutoresizingMaskIntoConstraints = false
        captureView.delegate = self
        captureView.captureSession.delegate = self
        captureVC.view.addSubview(captureView)

        let toolbar = buildToolbar(title: title)
        captureVC.view.addSubview(toolbar)

        NSLayoutConstraint.activate([
            captureView.topAnchor.constraint(equalTo: captureVC.view.topAnchor),
            captureView.leadingAnchor.constraint(equalTo: captureVC.view.leadingAnchor),
            captureView.trailingAnchor.constraint(equalTo: captureVC.view.trailingAnchor),
            captureView.bottomAnchor.constraint(equalTo: captureVC.view.bottomAnchor),
            toolbar.topAnchor.constraint(equalTo: captureVC.view.safeAreaLayoutGuide.topAnchor),
            toolbar.leadingAnchor.constraint(equalTo: captureVC.view.leadingAnchor),
            toolbar.trailingAnchor.constraint(equalTo: captureVC.view.trailingAnchor),
            toolbar.heightAnchor.constraint(equalToConstant: 52),
        ])

        self.captureView = captureView
        self.captureViewController = captureVC

        viewController.present(captureVC, animated: true) {
            captureView.captureSession.run(configuration: self.sessionConfig)
        }
    }

    private func buildToolbar(title: String) -> UIView {
        let toolbar = UIView()
        toolbar.translatesAutoresizingMaskIntoConstraints = false
        toolbar.backgroundColor = UIColor.black.withAlphaComponent(0.55)

        let cancelButton = UIButton(type: .system)
        cancelButton.setTitle("Cancel", for: .normal)
        cancelButton.tintColor = .white
        cancelButton.translatesAutoresizingMaskIntoConstraints = false
        cancelButton.addTarget(self, action: #selector(cancelTapped), for: .touchUpInside)

        let titleLabel = UILabel()
        titleLabel.text = title
        titleLabel.textColor = .white
        titleLabel.font = .boldSystemFont(ofSize: 15)
        titleLabel.translatesAutoresizingMaskIntoConstraints = false

        let doneButton = UIButton(type: .system)
        doneButton.setTitle("Done Room", for: .normal)
        doneButton.tintColor = .systemGreen
        doneButton.titleLabel?.font = .boldSystemFont(ofSize: 17)
        doneButton.translatesAutoresizingMaskIntoConstraints = false
        doneButton.addTarget(self, action: #selector(doneRoomTapped), for: .touchUpInside)

        toolbar.addSubview(cancelButton)
        toolbar.addSubview(titleLabel)
        toolbar.addSubview(doneButton)

        NSLayoutConstraint.activate([
            cancelButton.leadingAnchor.constraint(equalTo: toolbar.leadingAnchor, constant: 16),
            cancelButton.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
            titleLabel.centerXAnchor.constraint(equalTo: toolbar.centerXAnchor),
            titleLabel.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
            doneButton.trailingAnchor.constraint(equalTo: toolbar.trailingAnchor, constant: -16),
            doneButton.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
        ])
        return toolbar
    }

    private func finish(_ block: () -> Void) {
        guard !completed else { return }
        completed = true
        block()
    }

    @objc private func cancelTapped() {
        captureView?.captureSession.stop()
        dismissHost {
            self.finish {
                self.call.reject("Structure capture cancelled.")
                self.onFinished?()
            }
        }
    }

    @objc private func doneRoomTapped() {
        captureView?.captureSession.stop()
    }

    private func dismissHost(completion: (() -> Void)? = nil) {
        captureViewController?.dismiss(animated: true, completion: completion)
        captureView = nil
        captureViewController = nil
    }

    private func promptNextOrFinish() {
        guard let host = captureViewController else { return }

        let alert = UIAlertController(
            title: "Room \(roomCounter) saved",
            message: "Scan another room or finish the house structure.",
            preferredStyle: .alert
        )
        alert.addAction(UIAlertAction(title: "Next Room", style: .default) { _ in
            self.roomCounter += 1
            self.startNextRoomCapture()
        })
        alert.addAction(UIAlertAction(title: "Finish Structure", style: .default) { _ in
            self.resolveStructure()
        })
        host.present(alert, animated: true)
    }

    private func startNextRoomCapture() {
        captureView?.removeFromSuperview()
        guard let host = captureViewController else { return }

        let captureView = RoomCaptureView(frame: .zero)
        captureView.translatesAutoresizingMaskIntoConstraints = false
        captureView.delegate = self
        captureView.captureSession.delegate = self
        host.view.insertSubview(captureView, at: 0)

        NSLayoutConstraint.activate([
            captureView.topAnchor.constraint(equalTo: host.view.topAnchor),
            captureView.leadingAnchor.constraint(equalTo: host.view.leadingAnchor),
            captureView.trailingAnchor.constraint(equalTo: host.view.trailingAnchor),
            captureView.bottomAnchor.constraint(equalTo: host.view.bottomAnchor),
        ])

        self.captureView = captureView
        captureView.captureSession.run(configuration: sessionConfig)
    }

    private func resolveStructure() {
        guard !capturedRooms.isEmpty else {
            dismissHost {
                self.finish {
                    self.call.reject("No rooms captured.")
                    self.onFinished?()
                }
            }
            return
        }

        let structureId = UUID().uuidString.lowercased()
        let payload = RoomCaptureEncoder.encodeStructure(
            rooms: capturedRooms,
            labels: roomLabels,
            sections: roomSections,
            structureLabel: structureLabel,
            structureId: structureId
        )
        dismissHost {
            self.finish {
                self.call.resolve(payload)
                self.onFinished?()
            }
        }
    }

    func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
        if let error = error {
            dismissHost {
                self.finish {
                    self.call.reject("Structure capture failed: \(error.localizedDescription)")
                    self.onFinished?()
                }
            }
        }
    }

    func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool {
        if let error = error {
            dismissHost {
                self.finish {
                    self.call.reject("Structure capture failed: \(error.localizedDescription)")
                    self.onFinished?()
                }
            }
            return false
        }
        return true
    }

    func captureView(didPresent processedResult: CapturedRoom, error: Error?) {
        if let error = error {
            dismissHost {
                self.finish {
                    self.call.reject("Room processing failed: \(error.localizedDescription)")
                    self.onFinished?()
                }
            }
            return
        }

        capturedRooms.append(processedResult)
        roomLabels.append("Room \(roomCounter)")
        roomSections.append(nil)
        promptNextOrFinish()
    }
}
#endif
