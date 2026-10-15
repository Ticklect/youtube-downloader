//! Local channel suggestions from channels the user has actually loaded.
//! No inferred or remotely fetched channel identities are created here.

use crate::store::{SavedChannel, SavedChannelHistory, MAX_CHANNEL_HISTORY, MAX_SAVED_CHANNELS};

pub const MAX_RECOMMENDATIONS: usize = 6;

pub fn record_success(history: &mut Vec<SavedChannelHistory>, name: &str, url: &str) {
    // The load handler calls this only after yt-dlp returns a channel name and
    // video list. The canonical URL is validated before the load begins.
    let next = history
        .iter()
        .map(|entry| entry.last_opened)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    if let Some(entry) = history.iter_mut().find(|entry| entry.url == url) {
        entry.name = clean_name(name);
        entry.loads = entry.loads.saturating_add(1);
        entry.last_opened = next;
        return;
    }

    if history.len() >= MAX_CHANNEL_HISTORY {
        if let Some(oldest) = history
            .iter()
            .enumerate()
            .min_by_key(|(_, item)| (item.last_opened, item.loads))
            .map(|(index, _)| index)
        {
            history.remove(oldest);
        }
    }
    history.push(SavedChannelHistory {
        name: clean_name(name),
        url: url.to_owned(),
        loads: 1,
        last_opened: next,
    });
}

pub fn clean_name(name: &str) -> String {
    let name: String = name
        .chars()
        .filter(|ch| !ch.is_control())
        .take(100)
        .collect();
    let name = name.trim();
    if name.is_empty() {
        "YouTube channel".to_owned()
    } else {
        name.to_owned()
    }
}

pub fn suggested(history: &[SavedChannelHistory], saved: &[SavedChannel]) -> Vec<SavedChannel> {
    let mut candidates = history
        .iter()
        .filter(|entry| !saved.iter().any(|channel| channel.url == entry.url))
        .collect::<Vec<_>>();
    // Frequently loaded channels lead, with recent activity breaking ties.
    candidates.sort_unstable_by(|a, b| {
        b.loads
            .cmp(&a.loads)
            .then_with(|| b.last_opened.cmp(&a.last_opened))
            .then_with(|| a.url.cmp(&b.url))
    });
    candidates
        .into_iter()
        .take(MAX_RECOMMENDATIONS)
        .map(|entry| SavedChannel {
            name: entry.name.clone(),
            url: entry.url.clone(),
        })
        .collect()
}

pub fn add_saved(
    history: &[SavedChannelHistory],
    saved: &mut Vec<SavedChannel>,
    url: &str,
) -> bool {
    if saved.iter().any(|entry| entry.url == url) || saved.len() >= MAX_SAVED_CHANNELS {
        return false;
    }
    let Some(entry) = history.iter().find(|entry| entry.url == url) else {
        return false;
    };
    saved.push(SavedChannel {
        name: entry.name.clone(),
        url: entry.url.clone(),
    });
    true
}

pub fn remove_saved(saved: &mut Vec<SavedChannel>, url: &str) -> bool {
    let previous = saved.len();
    saved.retain(|entry| entry.url != url);
    previous != saved.len()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn visit(history: &mut Vec<SavedChannelHistory>, name: &str, handle: &str) {
        record_success(
            history,
            name,
            &format!("https://www.youtube.com/@{handle}/videos"),
        );
    }

    #[test]
    fn frequency_then_recency_determine_actual_history_suggestions() {
        let mut history = Vec::new();
        visit(&mut history, "Alpha", "alpha");
        visit(&mut history, "Beta", "beta");
        visit(&mut history, "Alpha updated", "alpha");
        visit(&mut history, "Gamma", "gamma");
        assert_eq!(
            suggested(&history, &[])
                .iter()
                .map(|entry| entry.name.as_str())
                .collect::<Vec<_>>(),
            vec!["Alpha updated", "Gamma", "Beta"]
        );
        assert_eq!(history.len(), 3);
        assert_eq!(history[0].loads, 2);
    }

    #[test]
    fn suggested_channel_can_be_saved_once_then_removed() {
        let mut history = Vec::new();
        visit(&mut history, "Creator", "creator");
        let mut saved = Vec::new();
        let url = history[0].url.clone();
        assert!(!add_saved(
            &history,
            &mut saved,
            "https://www.youtube.com/@fake/videos"
        ));
        assert!(add_saved(&history, &mut saved, &url));
        assert!(!add_saved(&history, &mut saved, &url));
        assert!(suggested(&history, &saved).is_empty());
        assert!(remove_saved(&mut saved, &url));
        assert!(!remove_saved(&mut saved, &url));
        assert_eq!(suggested(&history, &saved).len(), 1);
    }

    #[test]
    fn history_and_saved_channels_remain_bounded() {
        let mut history = Vec::new();
        for index in 0..(MAX_CHANNEL_HISTORY + 5) {
            visit(
                &mut history,
                &format!("Creator {index}"),
                &format!("c{index}"),
            );
        }
        assert_eq!(history.len(), MAX_CHANNEL_HISTORY);
        assert!(!history.iter().any(|entry| entry.name == "Creator 0"));
        assert!(history.iter().any(|entry| entry.name == "Creator 68"));
        assert_eq!(suggested(&history, &[]).len(), MAX_RECOMMENDATIONS);

        let mut saved = Vec::new();
        let urls = history
            .iter()
            .map(|item| item.url.clone())
            .collect::<Vec<_>>();
        for url in urls.iter().take(MAX_SAVED_CHANNELS) {
            assert!(add_saved(&history, &mut saved, url));
        }
        assert!(!add_saved(&history, &mut saved, &urls[MAX_SAVED_CHANNELS]));
        assert_eq!(saved.len(), MAX_SAVED_CHANNELS);
    }

    #[test]
    fn cleaned_names_cannot_inject_controls_into_ui() {
        let mut history = Vec::new();
        visit(&mut history, "Line\n break\t", "creator");
        assert_eq!(history[0].name, "Line break");
    }
}
