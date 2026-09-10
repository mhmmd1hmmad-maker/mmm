package com.smartarchive.app

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.smartarchive.app.databinding.ItemSourceBinding

class SourcesAdapter(private val items: List<SourceItem>) :
    RecyclerView.Adapter<SourcesAdapter.VH>() {

    class VH(val b: ItemSourceBinding) : RecyclerView.ViewHolder(b.root)

    override fun onCreateViewHolder(p: ViewGroup, t: Int) =
        VH(ItemSourceBinding.inflate(LayoutInflater.from(p.context), p, false))

    override fun getItemCount() = items.size

    override fun onBindViewHolder(h: VH, pos: Int) {
        val s = items[pos]
        h.b.tvSourceTitle.text = "📄 ${s.title} — صفحة ${s.page}"
        h.b.tvSourceText.text = s.text
    }
}
