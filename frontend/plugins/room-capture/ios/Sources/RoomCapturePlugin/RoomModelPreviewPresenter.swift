import Foundation
import UIKit
import Capacitor
import QuickLook

#if canImport(RoomPlan)
/// Presents the on-device QuickLook preview for a room's cached USDZ model.
/// QuickLook supplies its own preview UI and share action — no separate
/// share-sheet code needed.
final class RoomModelPreviewPresenter: NSObject, QLPreviewControllerDataSource, QLPreviewControllerDelegate {
    private let call: CAPPluginCall
    private let modelURL: URL
    private var onFinished: (() -> Void)?

    init(call: CAPPluginCall, modelURL: URL, onFinished: (() -> Void)? = nil) {
        self.call = call
        self.modelURL = modelURL
        self.onFinished = onFinished
        super.init()
    }

    func present(from viewController: UIViewController) {
        let preview = QLPreviewController()
        preview.dataSource = self
        preview.delegate = self
        preview.modalPresentationStyle = .fullScreen
        viewController.present(preview, animated: true) { [weak self] in
            self?.call.resolve(["previewed": true])
        }
    }

    func numberOfPreviewItems(in controller: QLPreviewController) -> Int {
        1
    }

    func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem {
        modelURL as NSURL
    }

    func previewControllerDidDismiss(_ controller: QLPreviewController) {
        onFinished?()
        onFinished = nil
    }
}
#endif
