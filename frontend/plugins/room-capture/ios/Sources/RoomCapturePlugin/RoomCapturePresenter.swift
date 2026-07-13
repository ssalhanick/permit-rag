import Foundation
import UIKit
import Capacitor
import AVFoundation

#if canImport(RoomPlan)
import RoomPlan

/// Presents RoomCaptureView and resolves the Capacitor plugin call with encoded JSON.
final class RoomCapturePresenter: NSObject, RoomCaptureViewDelegate, RoomCaptureSessionDelegate {
    private let call: CAPPluginCall
    private let roomLabel: String
    private var captureViewController: UIViewController?
    private var captureView: RoomCaptureView?
    private let sessionConfig = RoomCaptureSession.Configuration()
    private var onFinished: (() -> Void)?
    private var completed = false

    init(call: CAPPluginCall, roomLabel: String, onFinished: (() -> Void)? = nil) {
        self.call = call
        self.roomLabel = roomLabel
        self.onFinished = onFinished
        super.init()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func encode(with coder: NSCoder) {
        // RoomCaptureViewDelegate inherits NSCoding; stub only.
    }

    func present(from viewController: UIViewController) {
        let captureVC = UIViewController()
        captureVC.modalPresentationStyle = .fullScreen
        captureVC.view.backgroundColor = .black

        let captureView = RoomCaptureView(frame: .zero)
        captureView.translatesAutoresizingMaskIntoConstraints = false
        captureView.delegate = self
        captureView.captureSession.delegate = self
        captureVC.view.addSubview(captureView)

        let toolbar = UIView()
        toolbar.translatesAutoresizingMaskIntoConstraints = false
        toolbar.backgroundColor = UIColor.black.withAlphaComponent(0.55)
        captureVC.view.addSubview(toolbar)

        let cancelButton = UIButton(type: .system)
        cancelButton.setTitle("Cancel", for: .normal)
        cancelButton.tintColor = .white
        cancelButton.translatesAutoresizingMaskIntoConstraints = false
        cancelButton.addTarget(self, action: #selector(cancelTapped), for: .touchUpInside)

        let doneButton = UIButton(type: .system)
        doneButton.setTitle("Done", for: .normal)
        doneButton.tintColor = .systemGreen
        doneButton.titleLabel?.font = .boldSystemFont(ofSize: 17)
        doneButton.translatesAutoresizingMaskIntoConstraints = false
        doneButton.addTarget(self, action: #selector(doneTapped), for: .touchUpInside)

        toolbar.addSubview(cancelButton)
        toolbar.addSubview(doneButton)

        NSLayoutConstraint.activate([
            captureView.topAnchor.constraint(equalTo: captureVC.view.topAnchor),
            captureView.leadingAnchor.constraint(equalTo: captureVC.view.leadingAnchor),
            captureView.trailingAnchor.constraint(equalTo: captureVC.view.trailingAnchor),
            captureView.bottomAnchor.constraint(equalTo: captureVC.view.bottomAnchor),
            toolbar.topAnchor.constraint(equalTo: captureVC.view.safeAreaLayoutGuide.topAnchor),
            toolbar.leadingAnchor.constraint(equalTo: captureVC.view.leadingAnchor),
            toolbar.trailingAnchor.constraint(equalTo: captureVC.view.trailingAnchor),
            toolbar.heightAnchor.constraint(equalToConstant: 52),
            cancelButton.leadingAnchor.constraint(equalTo: toolbar.leadingAnchor, constant: 16),
            cancelButton.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
            doneButton.trailingAnchor.constraint(equalTo: toolbar.trailingAnchor, constant: -16),
            doneButton.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
        ])

        self.captureView = captureView
        self.captureViewController = captureVC

        viewController.present(captureVC, animated: true) {
            captureView.captureSession.run(configuration: self.sessionConfig)
        }
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
                self.call.reject("Room capture cancelled.")
                self.onFinished?()
            }
        }
    }

    @objc private func doneTapped() {
        captureView?.captureSession.stop()
    }

    private func dismissHost(completion: (() -> Void)? = nil) {
        captureViewController?.dismiss(animated: true, completion: completion)
        captureView = nil
        captureViewController = nil
    }

    // MARK: - RoomCaptureSessionDelegate

    func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
        if let error = error {
            dismissHost {
                self.finish {
                    self.call.reject("Room capture failed: \(error.localizedDescription)")
                    self.onFinished?()
                }
            }
        }
    }

    // MARK: - RoomCaptureViewDelegate

    func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool {
        if let error = error {
            dismissHost {
                self.finish {
                    self.call.reject("Room capture failed: \(error.localizedDescription)")
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

        let payload = RoomCaptureEncoder.encode(
            capturedRoom: processedResult,
            roomLabel: roomLabel,
            roomId: UUID().uuidString.lowercased()
        )
        dismissHost {
            self.finish {
                self.call.resolve(payload)
                self.onFinished?()
            }
        }
    }
}

/// LiDAR + RoomPlan availability check.
enum RoomPlanSupport {
    static func isAvailable() -> Bool {
        RoomCaptureSession.isSupported
    }

    static func unavailableReason() -> String {
        "RoomPlan needs iPhone Pro / iPad Pro with LiDAR (iOS 16+). Regular iPhone models do not have LiDAR."
    }
}
#endif
