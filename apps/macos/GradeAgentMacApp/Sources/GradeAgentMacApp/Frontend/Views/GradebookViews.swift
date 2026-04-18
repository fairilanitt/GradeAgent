import Foundation
import SwiftUI

struct GradebookPageView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        IntegratedPageSurface {
            VStack(alignment: .leading, spacing: 16) {
                header

                AdaptiveAxisStack(horizontal: !compact, spacing: 12) {
                    MiniInfoPill(label: "Selain", value: store.browserReady ? "Valmis" : "Ei auki")
                    MiniInfoPill(label: "Tila", value: store.gradebookRunning ? "Kysely käynnissä" : "Valmis kyselyyn")
                    if let lastAssistant = store.gradebookMessages.last(where: { $0.role == .assistant }) {
                        MiniInfoPill(label: "Skannatut kokeet", value: "\(lastAssistant.examsScanned)")
                        MiniInfoPill(label: "Osumat", value: "\(lastAssistant.examsMatched)")
                    }
                }

                transcript
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

                composer
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Arviointikirja")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.ink)
                Text("Kysy kokeista, opiskelijoista ja näkyvistä pistetiedoista. Arviointikirja käyttää samaa hallittua Sanoma-selainta ja kerää tiedot deterministisesti kokeiden listasta ja yleisnäkymistä.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)

            Button {
                store.clearGradebookConversation()
            } label: {
                Label("Tyhjennä", systemImage: "trash")
            }
            .buttonStyle(LiquidGlassButtonStyle(tint: Theme.neutral))
        }
    }

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    ForEach(store.gradebookMessages) { message in
                        GradebookMessageRow(message: message)
                            .id(message.id)
                    }
                }
                .padding(.trailing, 6)
            }
            .scrollIndicators(.visible)
            .onChange(of: store.gradebookMessages.count) { _, _ in
                if let lastID = store.gradebookMessages.last?.id {
                    withAnimation(.easeOut(duration: 0.2)) {
                        proxy.scrollTo(lastID, anchor: .bottom)
                    }
                }
            }
        }
    }

    private var composer: some View {
        WorkspaceCanvas(title: "Kysy Arviointikirjalta", subtitle: "Kirjoita luonnollinen kysymys. Esimerkiksi oppilaan arvosanat, näkyvät pisteet tai kokeiden suoriutuminen ajanjaksolla.") {
            VStack(alignment: .leading, spacing: 12) {
                TextEditor(text: $store.gradebookDraftQuestion)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .scrollContentBackground(.hidden)
                    .padding(12)
                    .frame(minHeight: 94, maxHeight: 120)
                    .background(Theme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(Theme.hairline, lineWidth: 1)
                    )
                    .foregroundStyle(Theme.ink)

                HStack(spacing: 10) {
                    Text("Arviointikirja siirtyy tarvittaessa julkaistujen kokeiden listaan, avaa yleisnäkymiä ja kokoaa vastauksen näkyvistä pisteistä.")
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(Theme.inkMuted)

                    Spacer(minLength: 0)

                    Button {
                        Task { await store.sendGradebookQuestion() }
                    } label: {
                        Label(store.gradebookRunning ? "Haetaan..." : "Lähetä", systemImage: store.gradebookRunning ? "hourglass" : "arrow.up.circle.fill")
                    }
                    .buttonStyle(LiquidGlassButtonStyle(tint: Theme.accent))
                    .disabled(!store.canSendGradebookQuestion)
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 210, alignment: .topLeading)
    }
}

private struct GradebookMessageRow: View {
    @EnvironmentObject private var store: GuiStore
    let message: GuiGradebookChatMessage

    var body: some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 8) {
            HStack {
                if message.role == .assistant {
                    messageLabel
                    Spacer(minLength: 0)
                } else {
                    Spacer(minLength: 0)
                    messageLabel
                }
            }

            if message.role == .assistant, !message.findings.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(message.findings) { finding in
                        GradebookFindingCard(finding: finding)
                    }
                }
                .frame(maxWidth: 760, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, alignment: message.role == .user ? .trailing : .leading)
    }

    private var messageLabel: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                PromptTag(title: message.role == .assistant ? "Arviointikirja" : "Kysymys")
                if let parserMode = message.parserMode, message.role == .assistant {
                    PromptTag(title: parserMode == "model" ? "Malliparsinta" : "Heuristinen parsinta")
                }
                if let modelLabel = message.modelLabel, !modelLabel.isEmpty, message.role == .assistant {
                    PromptTag(title: modelLabel)
                }
            }

            Text(store.redactedTextForDisplay(message.text))
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .foregroundStyle(Theme.ink)
                .textSelection(.enabled)
                .frame(maxWidth: 760, alignment: .leading)

            Text(message.timestamp.formatted(date: .abbreviated, time: .shortened))
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(message.role == .assistant ? Theme.surface : Theme.accent.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(
                    message.role == .assistant ? Theme.hairline : Theme.accent.opacity(0.25),
                    lineWidth: 1
                )
        )
        .shadow(color: Theme.shadow.opacity(0.4), radius: 5, x: 0, y: 2)
    }
}

private struct GradebookFindingCard: View {
    @EnvironmentObject private var store: GuiStore
    let finding: GuiGradebookExamResult

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(finding.assignmentTitle)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(Theme.ink)
                    Text(finding.assignmentDate)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(Theme.inkSoft)
                }
                Spacer(minLength: 0)
                PromptTag(title: totalScoreText)
            }

            AdaptiveAxisStack(horizontal: true, spacing: 10) {
                if let groupName = finding.groupName {
                    MiniInfoPill(label: "Ryhmä", value: groupName)
                }
                MiniInfoPill(label: "Opiskelija", value: store.visibleStudentName(finding.matchedStudentName))
                MiniInfoPill(label: "Merkinnät", value: "\(finding.reviewedScoreCount)")
                if let participationText = participationText {
                    MiniInfoPill(label: "Osallistuminen", value: participationText)
                }
            }

            if !finding.exerciseScores.isEmpty {
                ScrollView(.horizontal) {
                    HStack(spacing: 8) {
                        ForEach(finding.exerciseScores) { score in
                            PromptTag(title: scoreDisplay(score))
                        }
                    }
                }
                .scrollIndicators(.hidden)
            }

            if !finding.overviewURL.isEmpty {
                Text(finding.overviewURL)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(Theme.inkMuted)
                    .textSelection(.enabled)
                    .lineLimit(2)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Theme.surfaceAlt)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Theme.hairlineSoft, lineWidth: 1)
        )
    }

    private var totalScoreText: String {
        if let awarded = finding.totalScoreAwarded, let possible = finding.totalScorePossible {
            return "\(formatScore(awarded)) / \(formatScore(possible))"
        }
        return "Ei kokonaistulosta"
    }

    private var participationText: String? {
        if finding.participated == true {
            return "Osallistui"
        }
        if finding.participated == false {
            return "Ei osallistunut"
        }
        if let label = finding.participationLabel?.trimmingCharacters(in: .whitespacesAndNewlines), !label.isEmpty {
            return label
        }
        return nil
    }

    private func formatScore(_ value: Double) -> String {
        let rounded = value.rounded(.towardZero)
        if abs(rounded - value) < 0.0001 {
            return String(Int(rounded))
        }
        return String(format: "%.2f", value).replacingOccurrences(of: ",00", with: "")
    }

    private func scoreDisplay(_ score: GuiGradebookExerciseScore) -> String {
        let label: String
        if let categoryName = score.categoryName, let exerciseNumber = score.exerciseNumber {
            label = "\(categoryName) / \(exerciseNumber)"
        } else if let exerciseLabel = score.exerciseLabel, !exerciseLabel.isEmpty {
            label = exerciseLabel
        } else if let exerciseNumber = score.exerciseNumber {
            label = "Tehtävä \(exerciseNumber)"
        } else {
            label = "Tehtävä"
        }
        return "\(label): \(score.scoreText)"
    }
}
